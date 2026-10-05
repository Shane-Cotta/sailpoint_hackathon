"""`get_identity_access` -- everything one person can get into, grouped by kind."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from ..client import describe_api_error
from . import _team
from .search_identities import summarize_identity

log = logging.getLogger(__name__)

_KINDS = {
    "role": "roles",
    "roles": "roles",
    "access_profile": "access_profiles",
    "access_profiles": "access_profiles",
    "entitlement": "entitlements",
    "entitlements": "entitlements",
    "account": "accounts",
    "accounts": "accounts",
    "privileged": "privileged",
}


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="get_identity_access")
    def get_identity_access(identity: str, kind: str | None = None) -> dict[str, Any]:
        """List one person's roles, access profiles, entitlements and accounts.

        Use this to drill into a specific person -- typically someone flagged by
        `review_team_access` -- or whenever the user asks "what access does X
        have?", "which systems can X log into?", "is X an admin anywhere?".

        Args:
            identity: Name, email, username or identity id, e.g. `Adam Kennedy`.
            kind: Optionally return only one kind: `role`, `access_profile`,
                `entitlement`, `account`, or `privileged`. Omit for everything.

        Returns:
            `identity` (summary), and `access` with `roles`, `access_profiles`,
            `entitlements` (`"Source: name"` labels), `privileged`, and
            `accounts` as `{source: count}`. On an ambiguous name, `error` plus
            `candidates`.
        """
        wanted = None
        if kind:
            wanted = _KINDS.get(kind.strip().lower())
            if wanted is None:
                return {
                    "error": f"Unknown kind {kind!r}.",
                    "valid_kinds": ["role", "access_profile", "entitlement", "account", "privileged"],
                }

        try:
            document = _team.resolve_identity(identity, include_nested=True)
        except _team.IdentityNotResolved as exc:
            return exc.payload
        except Exception as exc:
            log.exception("get_identity_access failed")
            return {"error": describe_api_error(exc)}

        access = _team.summarize_access(document)
        if wanted:
            access = {wanted: access[wanted]}

        return {
            "identity": summarize_identity(document),
            "access": access,
        }
