"""`review_team_access` -- a manager's whole team, their access, and what to look at.

One call answers "review my team's access": it resolves the manager, pulls every
direct report with their nested access in a single search, and runs the
deterministic checks in `_team.team_flags` (leavers still holding access,
privileged access, access nobody else on the team has, access-count outliers,
entitlements with no role behind them).
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import describe_api_error
from . import _team
from .search_identities import summarize_identity

log = logging.getLogger(__name__)


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="review_team_access")
    def review_team_access(
        manager: str,
        include_access_items: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Review a manager's direct reports and their access, and flag what needs attention.

        Use this when a manager asks about their team: "review my team's access",
        "does anyone on my team have access they shouldn't?", "who reports to
        Adam Kennedy and what can they get into?". Returns the team roster with
        per-person access counts, the access most of the team shares (the
        baseline), and a prioritised list of flags, each with a one-sentence
        reason:

        * leaver_risk (high) -- inactive/terminated but still holding access
        * privileged_access -- holds access marked privileged
        * unique_access -- holds items nobody else on the team has
        * access_outlier -- far more access than the team median
        * no_roles (low) -- entitlements with no role behind them

        Follow up on a flagged person with `get_identity_access`, and on open
        review work with `get_manager_pending_reviews`.

        Args:
            manager: The manager's name, email, username or identity id, e.g.
                `Adam Kennedy` or `adam.kennedy@example.com`.
            include_access_items: Also list every role, access profile and
                entitlement per person. Much larger output -- only use for small
                teams or when the user wants the full detail.
            limit: Maximum direct reports to include, 1-250. Default 100.

        Returns:
            `manager`, `team_size`, `team` (roster), `baseline_access`, `flags`,
            and `summary` counts by flag severity. If the manager name is
            ambiguous, `error` plus `candidates` to choose from.
        """
        try:
            manager_doc = _team.resolve_identity(manager)
            reports = _team.fetch_direct_reports(manager_doc["id"], limit=limit)
        except _team.IdentityNotResolved as exc:
            return exc.payload
        except Exception as exc:
            log.exception("review_team_access failed")
            return {"error": describe_api_error(exc)}

        members = [_team.build_member(doc) for doc in reports]
        flags = _team.team_flags(members)

        team = []
        for member in members:
            entry = _team.roster_entry(member, flags)
            if include_access_items:
                access = member["access"]
                entry["access"] = {
                    key: access[key]
                    for key in ("roles", "access_profiles", "entitlements", "accounts")
                    if access.get(key)
                }
            team.append(entry)

        severity_counts: dict[str, int] = {}
        for flag in flags:
            severity_counts[flag["severity"]] = severity_counts.get(flag["severity"], 0) + 1

        response: dict[str, Any] = {
            "manager": summarize_identity(manager_doc),
            "team_size": len(members),
            "team": team,
            "baseline_access": _team.common_access(members),
            "flags": flags,
            "summary": {
                "flagged_people": len({f["identity"] for f in flags}),
                "flags_by_severity": severity_counts,
            },
        }
        if not members:
            response["note"] = (
                "No identities list this person as their manager. Check the name, "
                "or whether the tenant populates the manager attribute."
            )
        elif len(members) < _team.MIN_TEAM_FOR_PEER_FLAGS:
            response["note"] = (
                "Team is too small for peer comparison; unique_access and "
                "access_outlier checks were skipped."
            )
        elif len(members) >= max(1, min(limit, _team.MAX_TEAM_SIZE)):
            response["note"] = (
                f"Showing the first {len(members)} direct reports; raise `limit` to include more."
            )
        return response
