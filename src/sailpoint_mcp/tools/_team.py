"""Shared helpers for the manager team-access-review tools.

Starts with `_` so the auto-loader skips it -- it registers no tools itself.
Everything here except `resolve_identity` and `fetch_direct_reports` is a pure
function over search documents, so the review logic is unit-testable without a
tenant.

Search documents from the identities index carry a nested `access` array (roles,
access profiles and entitlements) and an `accounts` array when the request sets
`includeNested`. That is the whole data model the review works from: one search
call for the manager, one for the team.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any, Iterable

from sailpoint import SearchApi
from sailpoint.search.models.query import Query
from sailpoint.search.models.query_result_filter import QueryResultFilter
from sailpoint.search.models.search import Search

from ..client import call_sailpoint
from .search_identities import RESULT_FIELDS, _get, build_query_string, build_search

# Nested fields needed on top of the usual identity projection. Only the parts of
# each access item / account the review reads -- the full nested objects are big.
NESTED_FIELDS = [
    "access.id",
    "access.type",
    "access.name",
    "access.displayName",
    "access.privileged",
    "access.source.name",
    "accounts.id",
    "accounts.name",
    "accounts.disabled",
    "accounts.privileged",
    "accounts.source.name",
]
TEAM_FIELDS = RESULT_FIELDS + NESTED_FIELDS

# The Search API caps a page at 250; a "team" larger than that is an org, not a
# team, and would not fit in a model's context anyway.
MAX_TEAM_SIZE = 250

# Below this many people, "only one person has X" is not a meaningful signal.
MIN_TEAM_FOR_PEER_FLAGS = 3

# accessCount must exceed the team median by this factor (and by at least
# OUTLIER_MIN_GAP items) before a member is called an outlier.
OUTLIER_FACTOR = 1.5
OUTLIER_MIN_GAP = 3

# Share of the team that must hold an item for it to count as baseline access.
BASELINE_SHARE = 0.8

# Lifecycle states, lower-cased, that mean the person should not hold access.
_LEAVER_MARKERS = ("inactive", "terminat", "leaver", "disabled", "separated")

# Search API `type` values -> the keys used in our output.
_ACCESS_KINDS = {
    "ROLE": "roles",
    "ACCESS_PROFILE": "access_profiles",
    "ENTITLEMENT": "entitlements",
}

# Cap on how many unique items a single flag lists, to keep output small.
_MAX_ITEMS_PER_FLAG = 5


class IdentityNotResolved(Exception):
    """The query matched zero or several identities; `payload` explains which."""

    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload.get("error", "identity not resolved"))
        self.payload = payload


# --------------------------------------------------------------------------- #
# Tenant calls
# --------------------------------------------------------------------------- #


def pick_single(query: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the one matching document, or raise with something the model can act on.

    An exact (case-insensitive) display-name or username match wins even when the
    search returned several hits, so "Adam Kennedy" does not stall on
    "Adam Kennedy-Smith".
    """
    if not documents:
        raise IdentityNotResolved(
            {
                "error": f"No identity matched {query!r}.",
                "hint": "Try a partial name with a wildcard (e.g. `Adam*`) or an email address.",
            }
        )
    if len(documents) == 1:
        return documents[0]

    wanted = query.strip().strip('"').lower()
    exact = [
        d
        for d in documents
        if wanted
        in {
            str(d.get("displayName") or "").lower(),
            str(d.get("name") or "").lower(),
            str(d.get("email") or "").lower(),
        }
    ]
    if len(exact) == 1:
        return exact[0]

    raise IdentityNotResolved(
        {
            "error": f"{query!r} matched {len(documents)} identities; ask the user which one they mean.",
            "candidates": [
                {
                    "id": d.get("id"),
                    "name": d.get("displayName") or d.get("name"),
                    "email": d.get("email"),
                    "job_title": _get(d, "attributes.jobTitle"),
                    "department": _get(d, "attributes.department"),
                }
                for d in documents
            ],
        }
    )


def resolve_identity(query: str, *, include_nested: bool = False) -> dict[str, Any]:
    """Find exactly one identity by name, email, username or id.

    Raises `IdentityNotResolved` on zero or ambiguous matches; API errors
    propagate for the caller's `describe_api_error`.
    """
    query = query.strip()
    if not query:
        raise IdentityNotResolved({"error": "No identity name was given."})

    query_string = build_query_string(query)
    if include_nested:
        search = Search(
            indices=["identities"],
            query=Query(query=query_string),
            query_result_filter=QueryResultFilter(includes=TEAM_FIELDS),
            sort=["displayName", "id"],
            include_nested=True,
        )
    else:
        search = build_search(query_string, sort=["displayName", "id"])

    results = call_sailpoint(
        lambda client: SearchApi(client).search_post_v1(search=search, limit=5)
    )
    documents = [d for d in results or [] if isinstance(d, dict)]
    return pick_single(query, documents)


def direct_reports_search(manager_id: str) -> Search:
    """The `Search` body for everyone whose manager is `manager_id`, with access."""
    escaped = manager_id.replace('"', '\\"')
    return Search(
        indices=["identities"],
        query=Query(query=f'manager.id:"{escaped}"'),
        query_result_filter=QueryResultFilter(includes=TEAM_FIELDS),
        sort=["displayName", "id"],
        include_nested=True,
    )


def fetch_direct_reports(manager_id: str, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, MAX_TEAM_SIZE))
    search = direct_reports_search(manager_id)
    results = call_sailpoint(
        lambda client: SearchApi(client).search_post_v1(search=search, limit=limit)
    )
    return [d for d in results or [] if isinstance(d, dict)]


# --------------------------------------------------------------------------- #
# Pure shaping
# --------------------------------------------------------------------------- #


def access_label(item: dict[str, Any]) -> str:
    """Human-readable name for an access item: entitlements carry their source."""
    name = item.get("displayName") or item.get("name") or item.get("id") or "?"
    if item.get("type") == "ENTITLEMENT":
        source = _get(item, "source.name")
        if source:
            return f"{source}: {name}"
    return str(name)


def summarize_access(document: dict[str, Any]) -> dict[str, Any]:
    """Flatten an identity's nested `access` and `accounts` arrays.

    Returns `roles`, `access_profiles`, `entitlements` (sorted label lists),
    `privileged` (labels of privileged access items and accounts), and
    `accounts` as `{source name: account count}`.
    """
    grouped: dict[str, set[str]] = {key: set() for key in _ACCESS_KINDS.values()}
    privileged: set[str] = set()

    for item in document.get("access") or []:
        if not isinstance(item, dict):
            continue
        kind = _ACCESS_KINDS.get(str(item.get("type") or "").upper())
        if kind is None:
            continue
        label = access_label(item)
        grouped[kind].add(label)
        if item.get("privileged"):
            privileged.add(label)

    accounts: Counter[str] = Counter()
    disabled = 0
    for account in document.get("accounts") or []:
        if not isinstance(account, dict):
            continue
        source = _get(account, "source.name") or "Unknown source"
        accounts[source] += 1
        if account.get("disabled"):
            disabled += 1
        if account.get("privileged"):
            privileged.add(f"{source} account: {account.get('name') or account.get('id')}")

    summary: dict[str, Any] = {key: sorted(values) for key, values in grouped.items()}
    summary["privileged"] = sorted(privileged)
    summary["accounts"] = dict(sorted(accounts.items()))
    summary["disabled_accounts"] = disabled
    return summary


def build_member(document: dict[str, Any]) -> dict[str, Any]:
    """One team member: identity basics plus the flattened access."""
    access = summarize_access(document)
    access_count = document.get("accessCount")
    if access_count is None:
        access_count = sum(
            len(access[key]) for key in ("roles", "access_profiles", "entitlements")
        )
    return {
        "id": document.get("id"),
        "name": document.get("displayName") or document.get("name"),
        "email": document.get("email"),
        "job_title": _get(document, "attributes.jobTitle"),
        "department": _get(document, "attributes.department"),
        "lifecycle_state": document.get("lifecycleState")
        or _get(document, "attributes.cloudLifecycleState"),
        "inactive": bool(document.get("inactive")),
        "access_count": access_count,
        "access": access,
    }


def is_leaver(member: dict[str, Any]) -> bool:
    if member.get("inactive"):
        return True
    state = str(member.get("lifecycle_state") or "").lower()
    return any(marker in state for marker in _LEAVER_MARKERS)


def _access_keys(member: dict[str, Any]) -> set[str]:
    access = member.get("access") or {}
    return {
        f"{kind}|{label}"
        for kind in ("roles", "access_profiles", "entitlements")
        for label in access.get(kind) or []
    }


def common_access(members: list[dict[str, Any]], top: int = 10) -> list[dict[str, Any]]:
    """Access items held by at least half the team -- the team's baseline."""
    if not members:
        return []
    counts: Counter[str] = Counter()
    for member in members:
        counts.update(_access_keys(member))
    threshold = max(2, (len(members) + 1) // 2)
    # Sort explicitly: most_common() breaks ties by insertion order, which here
    # comes from set iteration and so changes between runs.
    baseline = [
        {"access": key.split("|", 1)[1], "kind": key.split("|", 1)[0], "held_by": n}
        for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if n >= threshold
    ]
    return baseline[:top]


def team_flags(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic, explainable review signals, most urgent first.

    Each flag is `{"severity", "type", "identity", "reason"}` plus optional
    `items`. The rules are deliberately simple so a manager can verify them:

    * leaver_risk       -- inactive/terminated but still holds access or accounts
    * privileged_access -- holds access flagged privileged in ISC; high severity
                           when nobody else on the team holds that item
    * unique_access     -- holds items no one else on the team (3+ people) holds
    * access_outlier    -- accessCount well above the team median (3+ people)
    * missing_baseline  -- lacks most of what the rest of the team has (3+
                           people) -- usually an onboarding or mover gap
    * no_roles          -- entitlements with no role behind them, only raised
                           when most of the team *does* get access via roles
    """
    flags: list[dict[str, Any]] = []
    peer_rules = len(members) >= MIN_TEAM_FOR_PEER_FLAGS

    holders: Counter[str] = Counter()
    for member in members:
        holders.update(_access_keys(member))

    counts = [m["access_count"] for m in members if isinstance(m.get("access_count"), int)]
    median = statistics.median(counts) if counts else 0

    # Items nearly everyone holds. Someone missing most of them stands out.
    baseline = {
        key
        for key, n in holders.items()
        if peer_rules and n >= BASELINE_SHARE * len(members)
    }
    # Only complain about "no roles" in a team that normally uses roles.
    team_uses_roles = (
        sum(1 for m in members if (m.get("access") or {}).get("roles")) * 2 >= len(members)
    )

    for member in members:
        name = member.get("name") or member.get("id")
        access = member.get("access") or {}
        total = member.get("access_count") or 0
        n_accounts = sum((access.get("accounts") or {}).values())
        keys = _access_keys(member)
        unique = sorted(key.split("|", 1)[1] for key in keys if holders[key] == 1)

        if is_leaver(member) and (total or n_accounts):
            flags.append(
                {
                    "severity": "high",
                    "type": "leaver_risk",
                    "identity": name,
                    "reason": (
                        f"Lifecycle state is {member.get('lifecycle_state') or 'inactive'} "
                        f"but still holds {total} access item(s) and {n_accounts} account(s)."
                    ),
                }
            )

        if access.get("privileged"):
            privileged_unique = (
                sorted(set(access["privileged"]) & set(unique)) if peer_rules else []
            )
            reason = f"Holds {len(access['privileged'])} privileged item(s)"
            if privileged_unique:
                reason += f", {len(privileged_unique)} of which no one else on the team has"
            flags.append(
                {
                    "severity": "high" if privileged_unique else "medium",
                    "type": "privileged_access",
                    "identity": name,
                    "reason": reason + ".",
                    "items": (privileged_unique or access["privileged"])[:_MAX_ITEMS_PER_FLAG],
                }
            )

        if peer_rules:
            if unique:
                flags.append(
                    {
                        "severity": "medium",
                        "type": "unique_access",
                        "identity": name,
                        "reason": f"Holds {len(unique)} item(s) no one else on the team has.",
                        "items": unique[:_MAX_ITEMS_PER_FLAG],
                    }
                )

            if (
                median
                and total > median * OUTLIER_FACTOR
                and total - median >= OUTLIER_MIN_GAP
            ):
                flags.append(
                    {
                        "severity": "medium",
                        "type": "access_outlier",
                        "identity": name,
                        "reason": f"Has {total} access items vs a team median of {median:g}.",
                    }
                )

            missing = sorted(key.split("|", 1)[1] for key in baseline - keys)
            if baseline and len(missing) * 2 > len(baseline):
                flags.append(
                    {
                        "severity": "low",
                        "type": "missing_baseline",
                        "identity": name,
                        "reason": (
                            f"Lacks {len(missing)} of the {len(baseline)} items nearly "
                            "everyone else on the team has -- possibly not fully onboarded."
                        ),
                        "items": missing[:_MAX_ITEMS_PER_FLAG],
                    }
                )

        if team_uses_roles and access.get("entitlements") and not access.get("roles"):
            flags.append(
                {
                    "severity": "low",
                    "type": "no_roles",
                    "identity": name,
                    "reason": (
                        f"Has {len(access['entitlements'])} entitlement(s) but no role, "
                        "unlike most of the team -- access was granted piecemeal."
                    ),
                }
            )

    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f["severity"]], str(f["identity"])))
    return flags


def roster_entry(member: dict[str, Any], flags: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compact per-member line for the team roster."""
    access = member.get("access") or {}
    flag_types = sorted({f["type"] for f in flags if f["identity"] == member.get("name")})
    entry = {
        "id": member.get("id"),
        "name": member.get("name"),
        "job_title": member.get("job_title"),
        "lifecycle_state": member.get("lifecycle_state"),
        "access_count": member.get("access_count"),
        "roles": len(access.get("roles") or []),
        "access_profiles": len(access.get("access_profiles") or []),
        "entitlements": len(access.get("entitlements") or []),
        "flags": flag_types,
    }
    return {k: v for k, v in entry.items() if v not in (None, [], "")}
