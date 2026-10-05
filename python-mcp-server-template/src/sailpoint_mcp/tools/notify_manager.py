"""`notify_manager` -- turn a review finding into an email to the person's manager.

Closes the loop on `review_team_access`: the finding is handed to the
"Flagged Report to Manager" workflow (identity-workflows/), which looks up the
person and their manager in ISC and sends the email. The workflow uses an
external trigger, so it runs only when this tool calls it -- never on tenant
events -- and it authenticates with the workflow's own OAuth client, not the
PAT (the external-trigger endpoint rejects PATs).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from mcp.server import MCPServer
from sailpoint import WorkflowsApi
from sailpoint.workflows.models.create_external_execute_workflow_v1_request import (
    CreateExternalExecuteWorkflowV1Request,
)

from ..client import call_sailpoint, call_sailpoint_as, describe_api_error
from ..config import ConfigError, load_flagged_workflow
from . import _team
from .search_identities import _get

log = logging.getLogger(__name__)

# Keep the email readable; the model sometimes passes a whole paragraph.
MAX_DETAIL_CHARS = 500

# The workflow has no wait steps and finishes in a few seconds; poll that long
# so the tool reports what actually happened, not just "trigger accepted".
POLL_SECONDS = 15
_FINAL_STATUSES = {"Completed", "Failed", "Canceled"}


def execution_status(execution_id: str) -> str | None:
    """Current status of a workflow execution (raw JSON: the SDK model rejects it)."""
    response = call_sailpoint(
        lambda client: WorkflowsApi(client).get_workflow_execution_v1_without_preload_content(
            id=execution_id
        )
    )
    if response.status != 200:
        return None
    return json.loads(response.data).get("status")


def wait_for_execution(execution_id: str, timeout: float = POLL_SECONDS) -> str | None:
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = execution_status(execution_id)
        if status in _FINAL_STATUSES:
            break
        time.sleep(1.5)
    return status


def build_trigger_input(identity_id: str, flag: str, detail: str) -> dict[str, str]:
    """The external trigger's input: `{identityId, flag, detail}`."""
    detail = " ".join(detail.split())
    if len(detail) > MAX_DETAIL_CHARS:
        detail = detail[: MAX_DETAIL_CHARS - 3] + "..."
    return {"identityId": identity_id, "flag": flag.strip(), "detail": detail}


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="notify_manager")
    def notify_manager(identity: str, flag: str, detail: str) -> dict[str, Any]:
        """Email a flagged person's manager about a team-access-review finding.

        This SENDS AN EMAIL. Only call it when the user explicitly asks to
        notify, alert or escalate to the manager -- never automatically after
        `review_team_access`. Confirm who and why first if it is unclear.

        Args:
            identity: The flagged person (name, email, username or id), e.g.
                `Brandon.Mason`.
            flag: The finding, short. Use the flag type and severity from
                `review_team_access`, e.g. `privileged_access (high)`.
            detail: One or two sentences the manager can act on, e.g. `Holds
                privileged Active Directory: AccountingGeneral that no one else
                on the team has.`

        Returns:
            `notified` (true once the workflow completed and sent the email),
            the identity and manager it was about, `workflow_status`, and the
            `workflow_execution_id` for audit. `error` on failure.
        """
        try:
            workflow_id, trigger_settings = load_flagged_workflow()
        except ConfigError as exc:
            return {"notified": False, "error": str(exc)}

        try:
            person = _team.resolve_identity(identity)
        except _team.IdentityNotResolved as exc:
            return {"notified": False, **exc.payload}
        except Exception as exc:
            log.exception("notify_manager: identity lookup failed")
            return {"notified": False, "error": describe_api_error(exc)}

        name = person.get("displayName") or person.get("name")
        manager = _get(person, "manager.displayName") or _get(person, "manager.name")
        if not manager:
            return {
                "notified": False,
                "identity": name,
                "error": f"{name} has no manager on record, so there is no one to notify.",
            }

        request = CreateExternalExecuteWorkflowV1Request(
            input=build_trigger_input(person["id"], flag, detail)
        )
        try:
            result = call_sailpoint_as(
                trigger_settings,
                lambda client: WorkflowsApi(client).create_external_execute_workflow_v1(
                    id=workflow_id,
                    create_external_execute_workflow_v1_request=request,
                ),
            )
        except Exception as exc:
            log.exception("notify_manager: workflow trigger failed")
            return {"notified": False, "identity": name, "error": describe_api_error(exc)}

        execution_id = getattr(result, "workflow_execution_id", None)
        log.info("notify_manager: %s (%s) -> execution %s", name, flag, execution_id)
        try:
            status = wait_for_execution(execution_id) if execution_id else None
        except Exception:  # status is best-effort; the trigger itself succeeded
            log.exception("notify_manager: could not read execution status")
            status = None

        response: dict[str, Any] = {
            "notified": status == "Completed",
            "identity": name,
            "manager": manager,
            "flag": flag,
            "workflow_status": status or "unknown",
            "workflow_execution_id": execution_id,
        }
        if status == "Completed":
            response["note"] = (
                "Email sent. In this demo tenant the workflow's recipient is the "
                "demo inbox, not the manager's real address."
            )
        elif status in _FINAL_STATUSES:
            response["error"] = (
                f"The notification workflow {status.lower()}; no email was sent. "
                "Check the execution in Admin > Workflows > Execution History."
            )
        else:
            response["note"] = "Workflow still running; the email should follow shortly."
        return response
