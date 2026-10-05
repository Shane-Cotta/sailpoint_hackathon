"""`get_manager_pending_reviews` -- open review work for a manager and their team.

Three sources, each fetched independently so one failing API (e.g. a 403 because
the PAT lacks a scope) does not hide the other two:

  * certifications this manager must still review,
  * the tenant's active certification campaigns,
  * access requests still executing (pending) for the manager's direct reports.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from mcp.server import MCPServer
from sailpoint import AccessRequestsApi, CertificationCampaignsApi, CertificationsApi

from ..client import call_sailpoint, describe_api_error
from . import _team
from .search_identities import _get

log = logging.getLogger(__name__)

# Per-report access-request lookups are one API call each; cap them.
MAX_REPORTS_FOR_REQUESTS = 25


def as_dict(model: Any) -> dict[str, Any]:
    """SDK model (or anyOf wrapper) -> plain camelCase dict.

    Uses pydantic's `model_dump`, not the SDK's `to_dict()`: the latter drops
    read-only fields, which here are the interesting ones (id, status, due,
    decisionsMade...).
    """
    if isinstance(model, dict):
        return model
    instance = getattr(model, "actual_instance", None)
    if instance is not None:
        model = instance
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump(by_alias=True, exclude_none=True, mode="json")
    to_dict = getattr(model, "to_dict", None)
    return to_dict() if callable(to_dict) else {}


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if v not in (None, [], {}, "")}


def summarize_certification(cert: dict[str, Any]) -> dict[str, Any]:
    made, total = cert.get("decisionsMade"), cert.get("decisionsTotal")
    progress = None
    if isinstance(made, int) and isinstance(total, int) and total:
        progress = f"{made}/{total} decisions ({round(100 * made / total)}%)"
    return _compact(
        {
            "id": cert.get("id"),
            "name": cert.get("name"),
            "campaign": _get(cert, "campaign.name"),
            "phase": cert.get("phase"),
            "due": cert.get("due"),
            "progress": progress,
            "identities": (
                f"{cert.get('identitiesCompleted')}/{cert.get('identitiesTotal')} reviewed"
                if cert.get("identitiesTotal")
                else None
            ),
        }
    )


def summarize_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "id": campaign.get("id"),
            "name": campaign.get("name"),
            "type": campaign.get("type"),
            "status": campaign.get("status"),
            "deadline": campaign.get("deadline"),
        }
    )


def summarize_request(request: dict[str, Any], requested_for: str | None) -> dict[str, Any]:
    return _compact(
        {
            "requested_for": requested_for or _get(request, "requestedFor.name"),
            "access": request.get("name"),
            "access_type": request.get("type"),
            "request_type": request.get("requestType"),
            "state": request.get("state"),
            "requested_by": _get(request, "requester.name"),
            "created": request.get("created"),
            "comment": _get(request, "requesterComment.comment"),
        }
    )


def _section(fetch: Callable[[], list[dict[str, Any]]], label: str) -> dict[str, Any]:
    try:
        items = fetch()
    except Exception as exc:
        log.exception("get_manager_pending_reviews: %s failed", label)
        return {"error": describe_api_error(exc), "items": []}
    return {"count": len(items), "items": items}


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="get_manager_pending_reviews")
    def get_manager_pending_reviews(manager: str, limit: int = 20) -> dict[str, Any]:
        """Show open review work for a manager: certifications, campaigns, pending access requests.

        Use when a manager asks "what do I need to review?", "do I have any open
        certifications?", "is anything pending for my team?", or after
        `review_team_access` to connect flagged access with in-flight reviews.

        Args:
            manager: The manager's name, email, username or identity id, e.g.
                `Adam Kennedy`.
            limit: Maximum items per section, 1-100. Default 20.

        Returns:
            `manager`, then three sections -- `my_certifications` (open
            certifications this manager reviews, with due date and progress),
            `active_campaigns`, and `team_pending_requests` (access requests
            still executing for direct reports). Each section has `count` and
            `items`, or `error` if that API was unavailable.
        """
        limit = max(1, min(limit, 100))

        try:
            manager_doc = _team.resolve_identity(manager)
        except _team.IdentityNotResolved as exc:
            return exc.payload
        except Exception as exc:
            log.exception("get_manager_pending_reviews failed")
            return {"error": describe_api_error(exc)}

        manager_id = manager_doc["id"]
        manager_name = manager_doc.get("displayName") or manager_doc.get("name")

        def certifications() -> list[dict[str, Any]]:
            certs = call_sailpoint(
                lambda client: CertificationsApi(client).list_identity_certifications_v1(
                    reviewer_identity=manager_id,
                    filters="completed eq false",
                    limit=limit,
                )
            )
            return [summarize_certification(as_dict(c)) for c in certs or []]

        def campaigns() -> list[dict[str, Any]]:
            found = call_sailpoint(
                lambda client: CertificationCampaignsApi(client).get_active_campaigns_v1(
                    filters='status eq "ACTIVE"', limit=limit
                )
            )
            return [summarize_campaign(as_dict(c)) for c in found or []]

        def team_requests() -> list[dict[str, Any]]:
            reports = _team.fetch_direct_reports(manager_id, limit=MAX_REPORTS_FOR_REQUESTS)
            pending: list[dict[str, Any]] = []
            for report in reports:
                report_name = report.get("displayName") or report.get("name")
                requests = call_sailpoint(
                    lambda client, rid=report["id"]: AccessRequestsApi(
                        client
                    ).list_access_request_status_v1(
                        requested_for=rid, request_state="EXECUTING", limit=limit
                    )
                )
                pending.extend(summarize_request(as_dict(r), report_name) for r in requests or [])
                if len(pending) >= limit:
                    break
            return pending[:limit]

        return {
            "manager": {"id": manager_id, "name": manager_name},
            "my_certifications": _section(certifications, "certifications"),
            "active_campaigns": _section(campaigns, "campaigns"),
            "team_pending_requests": _section(team_requests, "access requests"),
        }
