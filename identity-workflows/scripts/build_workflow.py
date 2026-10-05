#!/usr/bin/env python3
"""Build the Track 01 workflow definitions from the guide's template JSON.

Offline, stdlib only. Reads guide-files/workflows-hack-day-template.json (the
"Workflows Mini Hack Template" export published with the track) and writes:

  workflow/identity-onboarding.workflow.json
      The track deliverable: template + "Send Email" step (+ End step).
      Recipient is a PLACEHOLDER until you pass --recipient you@yourmail.

  workflow/identity-onboarding-to-manager.workflow.json
      Stretch goal "send it to the manager instead of yourself": same steps,
      recipient is the manager's email from Get Manager (fictional
      @navigate.example addresses in this tenant, so nothing reaches a human).

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

RECIPIENT_PLACEHOLDER = "REPLACE_WITH_YOUR_EMAIL@example.invalid"

# Internal step keys -> JSONPath roots: "Get Identity" -> $.getIdentity (Get New Hire),
# "Get Identity 1" -> $.getIdentity1 (Get Manager). See NOTES.md.
SUBJECT = "A new identity {{ $.getIdentity.attributes.displayName }} has been created in SHF"
BODY = (
    "A new identity has been created in SHF.\n"
    "\n"
    "  Name:        {{ $.getIdentity.attributes.displayName }}\n"
    "  Department:  {{ $.getIdentity.attributes.department }}\n"
    "  Job title:   {{ $.getIdentity.attributes.jobTitle }}\n"
    "  Reports to:  {{ $.getIdentity1.attributes.displayName }} ({{ $.getIdentity1.emailAddress }})\n"
)
MANAGER_SUBJECT = "Your new report {{ $.getIdentity.attributes.displayName }} starts in SHF"
MANAGER_BODY = (
    "Hi {{ $.getIdentity1.attributes.displayName }},\n"
    "\n"
    "{{ $.getIdentity.attributes.displayName }} has just been created in SHF and reports to you.\n"
    "\n"
    "  Department:  {{ $.getIdentity.attributes.department }}\n"
    "  Job title:   {{ $.getIdentity.attributes.jobTitle }}\n"
    "\n"
    "Please review the access they are given in their first week.\n"
)


def send_email_step(recipient_attr: dict, subject: str, body: str) -> dict:
    attrs = {"body": body, "context": {}, "subject": subject}
    attrs.update(recipient_attr)
    return {
        "actionId": "sp:send-email",
        "attributes": attrs,
        "displayName": "Send Onboarding Email",
        "nextStep": "End Step - Success",
        "type": "action",
        "versionNumber": 2,
    }


def build(template: dict, name: str, description: str, email_step: dict) -> dict:
    steps = copy.deepcopy(template["definition"]["steps"])
    # Template chain: Wait -> Get Identity -> Get Identity 1 -> End Step - Success
    steps["Get Identity 1"]["nextStep"] = "Send Email"
    steps["Send Email"] = email_step
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

    main_wf = build(
        template,
        f"{a.name} Identity Onboarding",
        "Hack Day Track 01: on idn:identity-created, look up the new hire and their manager and email an onboarding notice.",
        send_email_step({"recipientEmailList": [a.recipient]}, SUBJECT, BODY),
    )
    mgr_wf = build(
        template,
        f"{a.name} Identity Onboarding (to manager)",
        "Hack Day Track 01 stretch: same as Identity Onboarding but the notice goes to the new hire's manager.",
        send_email_step({"recipientEmailList.$": "$.getIdentity1.emailAddress"}, MANAGER_SUBJECT, MANAGER_BODY),
    )
    for fname, wf in (
        ("identity-onboarding.workflow.json", main_wf),
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
