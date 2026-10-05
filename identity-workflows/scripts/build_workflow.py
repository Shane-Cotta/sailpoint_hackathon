#!/usr/bin/env python3
"""Build the Track 01 workflow definitions from the guide's template JSON.

Offline, stdlib only. Reads guide-files/workflows-hack-day-template.json (the
"Workflows Mini Hack Template" export published with the track) and writes:

  workflow/identity-onboarding.workflow.json
      The track deliverable: template + "Send Email" step (+ End step).
      Recipient is a PLACEHOLDER until you pass --recipient you@yourmail.

  workflow/identity-onboarding-manager-check.workflow.json
      Stretch goal "survive a missing manager": a choice step skips Get Manager
      when managerRef.id is empty and sends a "routing to HR" notice instead.

  workflow/identity-onboarding-to-manager.workflow.json
      Stretch goal "send it to the manager instead of yourself" (+ the same
      manager check): recipient is the manager's email from Get Manager
      (fictional @navigate.example addresses here, so nothing reaches a human).

  workflow/flagged-report-to-manager.workflow.json
      Main-hack tie-in (design only, not created in the tenant): EXTERNAL trigger
      the manager-team-access-review MCP tools could call when review_team_access
      flags a report (leaver with access, privileged/outlier access, overdue
      certification). Looks up the report and manager, emails the manager.

Usage:
  python3 scripts/build_workflow.py [--recipient you@example.com] [--name "Your Name"]
"""
import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(ROOT, "guide-files", "workflows-hack-day-template.json")
OUT_DIR = os.path.join(ROOT, "workflow")

# RFC 2606 reserved domain: valid syntax (so the workflow saves and test-runs),
# undeliverable (null MX), and obviously a placeholder. Replace with your inbox.
RECIPIENT_PLACEHOLDER = "REPLACE_WITH_YOUR_EMAIL@example.com"

# Internal step keys -> JSONPath roots: "Get Identity" -> $.getIdentity (Get New Hire),
# "Get Identity 1" -> $.getIdentity1 (Get Manager). See NOTES.md.
SUBJECT = "A new identity {{ $.getIdentity.attributes.displayName }} has been created in SHF"
# The Send Email body is rendered as HTML (CoLab exports use <br/>), so plain
# newlines would collapse into one line. Each value needs its own {{ }}.
BODY = (
    "A new identity has been created in SHF.<br/><br/>"
    "Name: {{ $.getIdentity.attributes.displayName }}<br/>"
    "Department: {{ $.getIdentity.attributes.department }}<br/>"
    "Job title: {{ $.getIdentity.attributes.jobTitle }}<br/>"
    "Reports to: {{ $.getIdentity1.attributes.displayName }} ({{ $.getIdentity1.emailAddress }})"
)
NO_MANAGER_SUBJECT = "A new identity {{ $.getIdentity.attributes.displayName }} has no manager on record"
NO_MANAGER_BODY = (
    "A new identity has been created in SHF, but it has no manager on record, routing to HR.<br/><br/>"
    "Name: {{ $.getIdentity.attributes.displayName }}<br/>"
    "Department: {{ $.getIdentity.attributes.department }}<br/>"
    "Job title: {{ $.getIdentity.attributes.jobTitle }}"
)
MANAGER_SUBJECT = "Your new report {{ $.getIdentity.attributes.displayName }} starts in SHF"
MANAGER_BODY = (
    "Hi {{ $.getIdentity1.attributes.displayName }},<br/><br/>"
    "{{ $.getIdentity.attributes.displayName }} has just been created in SHF and reports to you.<br/><br/>"
    "Department: {{ $.getIdentity.attributes.department }}<br/>"
    "Job title: {{ $.getIdentity.attributes.jobTitle }}<br/><br/>"
    "Please review the access they are given in their first week."
)


def send_email_step(recipient_attr: dict, subject: str, body: str,
                    display="Send Onboarding Email", next_step="End Step - Success") -> dict:
    attrs = {"body": body, "context": {}, "subject": subject}
    attrs.update(recipient_attr)
    return {
        "actionId": "sp:send-email",
        "attributes": attrs,
        "displayName": display,
        "nextStep": next_step,
        "type": "action",
        "versionNumber": 2,
    }


def build(template: dict, name: str, description: str, email_step: dict, no_manager_step=None) -> dict:
    steps = copy.deepcopy(template["definition"]["steps"])
    # Template chain: Wait -> Get Identity -> Get Identity 1 -> End Step - Success
    steps["Get Identity 1"]["nextStep"] = "Send Email"
    steps["Send Email"] = email_step
    if no_manager_step is not None:
        # Stretch goal "survive a missing manager": only look the manager up
        # when Get New Hire returned a managerRef.id; otherwise take the
        # no-manager branch instead of failing in Get Manager.
        steps["Get Identity"]["nextStep"] = "Has Manager?"
        steps["Has Manager?"] = {
            "choiceList": [{
                "comparator": "IsPresent",
                "nextStep": "Get Identity 1",
                "variableA.$": "$.getIdentity.managerRef.id",
            }],
            "defaultStep": no_manager_step[0],
            "displayName": "Has Manager?",
            "type": "choice",
        }
        steps[no_manager_step[0]] = no_manager_step[1]
        steps.setdefault("End Step - No Manager", {"actionId": "sp:operator-success", "displayName": "", "type": "success"})
    return {
        "name": name,
        "description": description,
        "enabled": False,  # the API refuses to create enabled workflows; enable later (step 4)
        "definition": {"start": template["definition"]["start"], "steps": steps},
        "trigger": copy.deepcopy(template["trigger"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipient", default=os.environ.get("WF_RECIPIENT", RECIPIENT_PLACEHOLDER))
    ap.add_argument("--name", default=os.environ.get("WF_OWNER_NAME", "Shane Cotta"))
    a = ap.parse_args()

    with open(TEMPLATE) as f:
        template = json.load(f)
    os.makedirs(OUT_DIR, exist_ok=True)

    to_me = {"recipientEmailList": [a.recipient]}
    main_wf = build(
        template,
        f"{a.name} Identity Onboarding",
        "Hack Day Track 01: on idn:identity-created, look up the new hire and their manager and email an onboarding notice.",
        send_email_step(to_me, SUBJECT, BODY),
    )
    check_wf = build(
        template,
        f"{a.name} Identity Onboarding (manager check)",
        "Hack Day Track 01 stretch: same as Identity Onboarding, but identities without a manager get a 'routing to HR' notice instead of a failed run.",
        send_email_step(to_me, SUBJECT, BODY),
        ("Send Email No Manager", send_email_step(to_me, NO_MANAGER_SUBJECT, NO_MANAGER_BODY,
                                                  "Send No-Manager Email", "End Step - No Manager")),
    )
    mgr_wf = build(
        template,
        f"{a.name} Identity Onboarding (to manager)",
        "Hack Day Track 01 stretch: the onboarding notice goes to the new hire's manager; no manager means no email.",
        send_email_step({"recipientEmailList.$": "$.getIdentity1.emailAddress"}, MANAGER_SUBJECT, MANAGER_BODY,
                        "Email Manager"),
        ("End Step - No Manager", {"actionId": "sp:operator-success", "displayName": "", "type": "success"}),
    )
    flagged_wf = {
        "name": f"{a.name} Flagged Report to Manager",
        "description": "Main-hack tie-in: called by the team-access-review MCP server when a direct report is flagged; emails the report's manager.",
        "enabled": False,
        "definition": {
            "start": "Get Identity",
            "steps": {
                "Get Identity": {
                    "actionId": "sp:get-identity",
                    # External triggers deliver the POSTed body under `input`.
                    "attributes": {"id.$": "$.trigger.input.identityId"},
                    "displayName": "Get Flagged Report",
                    "nextStep": "Has Manager?",
                    "type": "action",
                    "versionNumber": 2,
                },
                "Has Manager?": {
                    "choiceList": [{"comparator": "IsPresent", "nextStep": "Get Identity 1",
                                    "variableA.$": "$.getIdentity.managerRef.id"}],
                    "defaultStep": "End Step - No Manager",
                    "displayName": "Has Manager?",
                    "type": "choice",
                },
                "Get Identity 1": {
                    "actionId": "sp:get-identity",
                    "attributes": {"id.$": "$.getIdentity.managerRef.id"},
                    "displayName": "Get Manager",
                    "nextStep": "Send Email",
                    "type": "action",
                    "versionNumber": 2,
                },
                "Send Email": send_email_step(
                    # Swap for {"recipientEmailList.$": "$.getIdentity1.emailAddress"} to mail the real manager.
                    {"recipientEmailList": [a.recipient]},
                    "Access review: {{ $.getIdentity.attributes.displayName }} was flagged ({{ $.trigger.input.flag }})",
                    "Hi {{ $.getIdentity1.attributes.displayName }},<br/><br/>"
                    "Your report {{ $.getIdentity.attributes.displayName }} "
                    "({{ $.getIdentity.attributes.department }}, {{ $.getIdentity.attributes.jobTitle }}) "
                    "was flagged in a team access review.<br/><br/>"
                    "Reason: {{ $.trigger.input.flag }}<br/>Details: {{ $.trigger.input.detail }}<br/><br/>"
                    "Please review their access or revoke it in the open certification.",
                    "Email Manager",
                ),
                "End Step - Success": {"actionId": "sp:operator-success", "displayName": "", "type": "success"},
                "End Step - No Manager": {"actionId": "sp:operator-success", "displayName": "", "type": "success"},
            },
        },
        "trigger": {"type": "EXTERNAL", "attributes": {
            "name": "flagged-report-to-manager",
            "description": "Input: {identityId, flag, detail}",
        }},
    }
    for fname, wf in (
        ("flagged-report-to-manager.workflow.json", flagged_wf),
        ("identity-onboarding.workflow.json", main_wf),
        ("identity-onboarding-manager-check.workflow.json", check_wf),
        ("identity-onboarding-to-manager.workflow.json", mgr_wf),
    ):
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w") as f:
            json.dump(wf, f, indent=2)
            f.write("\n")
        print("wrote", os.path.relpath(path, ROOT))
    if a.recipient == RECIPIENT_PLACEHOLDER:
        print("NOTE: recipient is a placeholder; re-run with --recipient you@yourmail before uploading.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
