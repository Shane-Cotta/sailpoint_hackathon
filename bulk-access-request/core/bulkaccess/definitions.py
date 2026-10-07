"""Pure builders for the SailPoint objects both deployments install.

Nothing here calls the API: given a Config (and IDs the installer looked up),
each function returns the exact JSON body to send. That keeps the definitions
unit-testable and lets `install.py --dry-run` print what would be created.

Two workflow variants share one definition (`bulk_workflow`):

* "launcher" -- started by a Launcher in the Launchpad. An Interactive Form
  collects the request from whoever launched it; results are reported back as
  Interactive Messages and email.
* "plugin"   -- started by the Bulk Access UI plugin through the workflow test
  endpoint (a browser plugin cannot hold external-trigger secrets). The plugin
  passes the same fields as trigger input. Must stay DISABLED.

Everything below was confirmed against a live tenant (see INSTALL.md
"How it works"): REGEX validation shape, STATIC options carrying full access
objects, Generic Approval encoding, and Manage Access inside one loop over the
people (SailPoint rejects nested loops and caps a request at 10 recipients, so
one request per person -- each with all the chosen items -- has no limits).
"""

from __future__ import annotations

import json
from typing import Any

from .config import Config
from .rules import APPROVAL_COMMENT_MAX, APPROVAL_DESCRIPTION_MAX

VARIANTS = ("launcher", "plugin")

# Form field keys (also the plugin's trigger input names).
F_PEOPLE, F_ITEMS, F_APPROVER, F_INC, F_JUSTIFICATION = "people", "items", "approver", "inc", "justification"


def _owner(owner_id: str, owner_name: str | None = None) -> dict[str, Any]:
    return {"type": "IDENTITY", "id": owner_id, **({"name": owner_name} if owner_name else {})}


# ───────────────────────────────────────────────────────────────── form ──
def bulk_form(cfg: Config, owner_id: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    """The intake form shown in the Launchpad."""
    required = [{"validationType": "REQUIRED"}]
    elements = [
        {"id": "people", "key": F_PEOPLE, "elementType": "SELECT", "validations": required,
         "config": {"label": "People who need the access", "maximum": cfg.people_max, "forceSelect": True,
                    "helpText": f"Search and add up to {cfg.people_max} people.",
                    "dataSource": {"dataSourceType": "INTERNAL", "config": {"objectType": "IDENTITY"}}}},
        {"id": "items", "key": F_ITEMS, "elementType": "SELECT", "validations": required,
         "config": {"label": "Access to request", "maximum": cfg.catalog_max_items, "forceSelect": True,
                    "helpText": "Items from the Request Center catalog. Everyone above gets every item chosen here.",
                    "dataSource": {"dataSourceType": "STATIC", "config": {"options": options}}}},
        {"id": "approver", "key": F_APPROVER, "elementType": "SELECT", "validations": required,
         "config": {"label": "Approver", "maximum": 1, "forceSelect": True,
                    "helpText": "One person approves or denies the whole request. It can't be you.",
                    "dataSource": {"dataSourceType": "INTERNAL", "config": {"objectType": "IDENTITY"}}}},
        {"id": "inc", "key": F_INC, "elementType": "TEXT",
         "validations": required + [{"validationType": "REGEX",
                                     "config": {"regex": cfg.inc_pattern, "message": cfg.inc_message}}],
         "config": {"label": "ServiceNow incident (INC) number", "placeholder": cfg.inc_example,
                    "helpText": cfg.inc_message}},
        {"id": "justification", "key": F_JUSTIFICATION, "elementType": "TEXTAREA", "validations": required,
         "config": {"label": "Business justification", "rows": 3,
                    "helpText": "Shown to the approver and stored on every access request."}},
    ]
    return {
        "name": cfg.form_name,
        "description": f"{cfg.prefix}: request access for several people at once, approved by one person, "
                       f"tracked by a ServiceNow INC number.",
        "owner": _owner(owner_id),
        "formInput": [],
        "formElements": [{"id": "section", "elementType": "SECTION",
                          "config": {"label": "Bulk access request", "formElements": elements}}],
    }


# ───────────────────────────────────────────────────────────── workflow ──
def _paths(variant: str) -> dict[str, str]:
    if variant == "launcher":
        base = "$.interactiveForm.formData"
        return {"people": f"{base}.{F_PEOPLE}", "items": f"{base}.{F_ITEMS}", "approver": f"{base}.{F_APPROVER}",
                "inc": f"{base}.{F_INC}", "justification": f"{base}.{F_JUSTIFICATION}",
                "requester": "$.trigger.launchedBy.id"}
    if variant == "plugin":
        return {"people": "$.trigger.people", "items": "$.trigger.items", "approver": "$.trigger.approverId",
                "inc": "$.trigger.inc", "justification": "$.trigger.justification",
                "requester": "$.trigger.requesterId"}
    raise ValueError(f"variant must be one of {VARIANTS}")


def _t(path: str) -> str:
    """Template a JSONPath into a string attribute: "{{$.x}}"."""
    return "{{" + path + "}}"


def _success() -> dict[str, Any]:
    return {"actionId": "sp:operator-success", "type": "success", "displayName": ""}


def _failure() -> dict[str, Any]:
    return {"actionId": "sp:operator-failure", "type": "failure", "displayName": ""}


def _email(cfg: Config, subject: str, body: str, *, cc_approver: bool) -> dict[str, Any]:
    attrs: dict[str, Any] = {"subject": subject, "body": body, "context": {}}
    if cfg.override_recipients:
        attrs["recipientEmailList"] = list(cfg.override_recipients)   # demo/test tenants: never mail real people
    else:
        attrs["recipientEmailList.$"] = "$.getRequester.attributes.email"
        if cc_approver and cfg.cc_approver:
            attrs["carbonCopy.$"] = "$.getApprover.attributes.email"
    return {"actionId": "sp:send-email", "type": "action", "versionNumber": 2, "attributes": attrs}


def bulk_workflow(cfg: Config, *, variant: str, owner_id: str, owner_name: str | None = None,
                  form_id: str | None = None, workflow_id: str | None = None) -> dict[str, Any]:
    """The bulk-request workflow. `workflow_id` (known after creation) scopes the launcher trigger."""
    p = _paths(variant)
    inc, who, appr = _t(p["inc"]), _t("$.getRequester.attributes.displayName"), _t("$.getApprover.attributes.displayName")
    summary = f"INC {inc} · requested by {who} · approver {appr}"
    item_comment = f"{inc} | Bulk access request by {who} | Approved by {appr} | {_t(p['justification'])}"
    live = cfg.live
    mode_note = "" if live else " (DRY RUN: nothing was requested)"

    steps: dict[str, Any] = {}
    start = "Get Requester"

    if variant == "launcher":
        if not form_id:
            raise ValueError("form_id is required for the launcher variant")
        start = "Interactive Form"
        steps["Interactive Form"] = {
            "actionId": "sp:interactive-form", "type": "action", "versionNumber": 1, "displayName": "Bulk request form",
            "attributes": {"formDefinitionId": form_id, "interactiveProcessId.$": "$.trigger.interactiveProcessId",
                           "ownerId.$": "$.trigger.launchedBy.id", "title": cfg.base_name,
                           "message": "<p>Request access for several people at once. One approver decides the "
                                      "whole request, and the ServiceNow INC number is recorded on every item.</p>"},
            "nextStep": "Get Requester"}

    steps["Get Requester"] = {"actionId": "sp:get-identity", "type": "action", "versionNumber": 2,
                              "displayName": "Requester", "attributes": {"id.$": p["requester"]}, "nextStep": "Get Approver"}
    steps["Get Approver"] = {"actionId": "sp:get-identity", "type": "action", "versionNumber": 2,
                             "displayName": "Approver", "attributes": {"id.$": p["approver"]}, "nextStep": "Approver Is Requester?"}

    # Defence in depth: the form/plugin already enforce both of these.
    steps["Approver Is Requester?"] = {
        "actionId": "sp:compare-strings", "type": "choice", "displayName": "Approver is the requester?",
        "choiceList": [{"comparator": "StringEquals", "variableA.$": p["approver"], "variableB.$": p["requester"],
                        "nextStep": "Reject Self Approval"}],
        "defaultStep": "INC Valid?"}
    steps["INC Valid?"] = {
        "actionId": "sp:compare-strings", "type": "choice", "displayName": "INC number valid?",
        "choiceList": [{"comparator": "StringMatches", "variableA.$": p["inc"], "variableB": cfg.inc_pattern,
                        "nextStep": "Notify Pending" if variant == "launcher" else "Bulk Approval"}],
        "defaultStep": "Reject Bad INC"}

    def stop(name: str, title: str, message: str) -> None:
        if variant == "launcher":
            steps[name] = {"actionId": "sp:interactive-message", "type": "action", "versionNumber": 1, "displayName": title,
                           "attributes": {"category": "ERROR", "interactiveProcessId.$": "$.trigger.interactiveProcessId",
                                          "ownerId.$": "$.trigger.launchedBy.id", "title": title, "message": f"<p>{message}</p>"},
                           "nextStep": "End Step - Rejected"}
        else:
            steps[name] = {**_email(cfg, f"{cfg.base_name}: {title}", f"<p>{message}</p>", cc_approver=False),
                           "displayName": title, "nextStep": "End Step - Rejected"}

    stop("Reject Self Approval", "Choose a different approver",
         "You can't approve your own bulk request. Start again and choose someone else as the approver.")
    stop("Reject Bad INC", "Invalid INC number", cfg.inc_message)

    if variant == "launcher":
        steps["Notify Pending"] = {
            "actionId": "sp:interactive-message", "type": "action", "versionNumber": 1, "displayName": "Submitted",
            "attributes": {"category": "INFO", "interactiveProcessId.$": "$.trigger.interactiveProcessId",
                           "ownerId.$": "$.trigger.launchedBy.id", "title": f"Sent to {appr} for approval",
                           "message": f"<p>Your bulk request <b>{inc}</b> is waiting for {appr}. "
                                      f"You'll get an email when it's decided{mode_note}.</p>"},
            "nextStep": "Bulk Approval"}

    steps["Bulk Approval"] = {
        "actionId": "sp:generic-approval", "type": "action", "versionNumber": 1, "displayName": "One approval for the whole request",
        "attributes": {
            "name": f"Bulk access {inc}",
            "description": f"{cfg.prefix} bulk access request {inc} from {who}",
            "comments": f"{inc}: {_t(p['justification'])}",
            "requestedBy": "IDENTITY", "byIdentity.$": p["requester"],
            "requestedFor": "IDENTITY", "forIdentity.$": p["requester"],
            "approvalType": "SINGLE", "singleApproverCategory": "IDENTITY", "singleApproverIdentityId.$": p["approver"],
            "approvalReminder": "false", "approvalTimeout": cfg.approval_timeout_days,
            "approvalActionAtTimeout": cfg.approval_action_at_timeout, "priority": cfg.approval_priority},
        "nextStep": "Approved?"}
    steps["Approved?"] = {
        "actionId": "sp:compare-strings", "type": "choice", "displayName": "Approved?",
        "choiceList": [{"comparator": "StringEquals", "variableA.$": "$.bulkApproval.status", "variableB": "APPROVED",
                        "nextStep": "Request Access" if live else "Email Approved"}],
        "defaultStep": "Email Denied"}

    if live:
        # One loop over the people; each iteration requests every chosen item for one
        # person. (No nested loops in SailPoint workflows, and max 10 recipients per request.)
        steps["Request Access"] = {
            "actionId": "sp:loop:iterator", "type": "action", "versionNumber": 1, "displayName": "Request access per person",
            "attributes": {"input.$": p["people"], "context.$": p["items"], "start": "Manage Access",
                           "steps": {"Manage Access": {
                               "actionId": "sp:access:manage", "type": "action", "versionNumber": 1,
                               "attributes": {"requestType": "GRANT_ACCESS", "addIdentities.$": "$.loop.loopInput",
                                              "requestedItems.$": "$.loop.context", "comments": item_comment},
                               "nextStep": "End Step - Success Item"},
                               "End Step - Success Item": {"type": "success"}}},
            "nextStep": "Email Approved"}

    steps["Email Approved"] = {
        **_email(cfg, f"Approved: bulk access {inc}{mode_note}",
                 f"<p>Your bulk access request <b>{inc}</b> was approved by {appr}.</p>"
                 f"<p>{'Access was requested for every person and item on the request.' if live else 'DRY RUN: this installation is in dry-run mode, so nothing was requested.'}</p>"
                 f"<p>Justification: {_t(p['justification'])}</p>", cc_approver=True),
        "displayName": "Email: approved", "nextStep": "End Step - Success"}
    steps["Email Denied"] = {
        **_email(cfg, f"Denied: bulk access {inc}",
                 f"<p>Your bulk access request <b>{inc}</b> was not approved by {appr} "
                 f"(status: {_t('$.bulkApproval.status')}). Nothing was requested.</p>", cc_approver=True),
        "displayName": "Email: denied", "nextStep": "End Step - Success"}
    steps["End Step - Success"] = _success()
    steps["End Step - Rejected"] = _failure()

    if variant == "launcher":
        trigger: dict[str, Any] = {"type": "EVENT", "attributes": {"id": "idn:interactive-process-launched"}}
        if workflow_id:
            # The event fires for every launcher in the tenant; only react to our own.
            trigger["attributes"]["filter.$"] = f"$[?(@.workflowId == '{workflow_id}')]"
        description = (f"{cfg.prefix} Bulk Access Request ({cfg.mode}). Started by the '{cfg.launcher_name}' "
                       "Launcher. Installed by bulk-access-request/launcher/install.py.")
        name = cfg.launcher_workflow_name
    else:
        trigger = {"type": "EXTERNAL", "attributes": {"name": f"{cfg.plugin_alias}-workflow",
                                                      "description": "Input: people[], items[], approverId, requesterId, inc, justification"}}
        description = (f"{cfg.prefix} Bulk Access Request for the UI plugin ({cfg.mode}). Started through the "
                       "workflow test endpoint, so it must stay DISABLED. Installed by bulk-access-request/plugin/install.py.")
        name = cfg.plugin_workflow_name

    return {"name": name, "description": description[:APPROVAL_DESCRIPTION_MAX * 3],
            "owner": _owner(owner_id, owner_name), "enabled": False,
            "definition": {"start": start, "steps": steps}, "trigger": trigger}


# ───────────────────────────────────────────────────────────── launcher ──
def bulk_launcher(cfg: Config, workflow_id: str) -> dict[str, Any]:
    return {
        "name": cfg.launcher_name,
        "description": "Request access for several people at once from the Request Center catalog. One approver "
                       "decides the whole request; a ServiceNow INC number is required and recorded on every item.",
        "type": "INTERACTIVE_PROCESS",
        "disabled": False,
        "reference": {"type": "WORKFLOW", "id": workflow_id},
        "config": "{}",
    }


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=False)


__all__ = ["bulk_form", "bulk_workflow", "bulk_launcher", "VARIANTS", "APPROVAL_COMMENT_MAX"]
