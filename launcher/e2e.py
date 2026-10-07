#!/usr/bin/env python3
"""End-to-end test of the Launcher deployment, driven entirely through the API.

    python launcher/e2e.py --config config/<tenant>.json \\
        --people <identityId>,<identityId> --approver <identityId> --scenario approve

What it does, as the PAT user (who must be allowed to launch the Launcher):
  1. starts the Launcher                         (POST /v2025/launchers/{id}/launch)
  2. fills in and submits the intake form        (PATCH /v2025/form-instances/{id})
  3. finds the ONE approval, checks it went to --approver, and approves or
     rejects it on their behalf (ORG_ADMIN)      (POST /v2025/generic-approvals/{id}/approve|reject)
  4. waits for the workflow run and checks the outcome; in live mode, checks
     every person got an access request with the INC in its comment.

Use only test identities and test items: approved runs really request access when
the config's mode is "live". Every run uses a fresh random INC number.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bulkaccess import config as config_mod  # noqa: E402
from bulkaccess.tenant import Tenant, TenantError  # noqa: E402
import install  # noqa: E402  (reuse its find_* helpers)


def wait(fn, what: str, timeout: float = 120, every: float = 3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(every)
    raise SystemExit(f"FAIL: timed out waiting for {what}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--people", required=True, help="comma-separated identity IDs (test identities only)")
    ap.add_argument("--approver", required=True, help="identity ID of the approver (not the PAT user)")
    ap.add_argument("--justification", default="", help="override the justification text (e.g. to test long input)")
    ap.add_argument("--before-decision", default="",
                    help="shell command to run once the approval exists, before deciding it (e.g. take screenshots); "
                         "gets IPID and INC in its environment")
    ap.add_argument("--scenario", choices=["approve", "deny", "self"], default="approve",
                    help="self = the requester names themselves as approver; must be stopped before any approval")
    a = ap.parse_args(argv)

    cfg = config_mod.load(a.config)
    t = Tenant.from_env(cfg.env_file)
    me = t.me()
    people = [p.strip() for p in a.people.split(",") if p.strip()]
    inc = f"INC{random.randint(0, 9_999_999):07d}"
    print(f"Tenant {t.tenant_name} · mode {cfg.mode} · scenario {a.scenario} · {inc} · {len(people)} people")

    form = install.find_form(t, cfg.form_name)
    wf = install.find_workflow(t, cfg.launcher_workflow_name)
    launcher = install.find_launcher(t, cfg.launcher_name)
    if not (form and wf and launcher):
        raise SystemExit("FAIL: not installed. Run launcher/install.py first.")
    item_options = form["formElements"][0]["config"]["formElements"][1]["config"]["dataSource"]["config"]["options"]
    items = [o["value"] for o in item_options]
    print(f"Items on the form: {[i['name'] for i in items]}")

    # 1. Launch
    from datetime import datetime, timezone
    from datetime import timedelta
    # 20 s of slack for clock differences between this machine and the tenant.
    launched_at = (datetime.now(timezone.utc) - timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%S")
    started = t.call("POST", f"/v2025/launchers/{launcher['id']}/launch", {})
    ipid = started.get("interactiveProcessId")
    print(f"1. Launched: interactive process {ipid}")

    # 2. Find the form instance assigned to us and submit it
    def instance():
        res = t.call("GET", "/v2025/form-instances?limit=50") or {}
        rows = res.get("results") if isinstance(res, dict) else res
        # Only a form created by *this* launch: an older open form (e.g. one a person left
        # half-filled in the Launchpad) must never be picked up and submitted.
        mine = [r for r in rows or [] if r.get("formDefinitionId") == form["id"]
                and r.get("state") in ("ASSIGNED", "IN_PROGRESS") and r.get("created", "")[:19] >= launched_at]
        mine.sort(key=lambda r: r.get("created", ""), reverse=True)
        return mine[0] if mine else None
    inst = wait(instance, "the form to be assigned")
    approver = me["id"] if a.scenario == "self" else a.approver
    form_data = {"people": people, "items": items, "approver": [approver], "inc": inc,
                 "justification": a.justification or f"E2E test {inc} ({a.scenario}) by launcher/e2e.py"}
    # A form moves ASSIGNED -> IN_PROGRESS -> SUBMITTED; one PATCH may only advance it one
    # step, so repeat until it reports SUBMITTED.
    for _ in range(3):
        result = t.call("PATCH", f"/v2025/form-instances/{inst['id']}", [
            {"op": "replace", "path": "/formData", "value": form_data},
            {"op": "replace", "path": "/state", "value": "SUBMITTED"},
        ], content_type="application/json-patch+json")
        if (result or {}).get("state") == "SUBMITTED":
            break
    else:
        raise SystemExit(f"FAIL: form {inst['id']} would not submit (state {(result or {}).get('state')})")
    print(f"2. Form {inst['id']} submitted")

    if a.scenario == "self":
        def stopped():
            runs = t.call("GET", f"/v2025/workflows/{wf['id']}/executions?limit=5") or []
            return next((r for r in runs if r.get("status") in ("Completed", "Failed") and r.get("startTime", "")[:19] >= launched_at), None)
        run = wait(stopped, "the workflow run to stop", timeout=180)
        hist = t.call("GET", f"/v2025/workflow-executions/{run['id']}/history") or []
        done = [h["attributes"].get("stepName") for h in hist if h.get("type") == "ActivityTaskCompleted"]
        ok = "rejectSelfApproval" in done and "bulkApproval" not in done
        print(f"3. Run {run['id']}: {run['status']}; steps: {done}")
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1

    # 3. The one approval
    name = f"Bulk access {inc}"
    def approval():
        rows = t.call("GET", "/v2025/generic-approvals?limit=100") or []
        return next((r for r in rows if (r.get("name") or [{}])[0].get("value") == name and r.get("status") == "PENDING"), None)
    appr = wait(approval, f"approval '{name}'")
    assignees = [x.get("identityID") for x in appr.get("assignedTo") or []]
    if a.approver not in assignees:
        t.call("POST", "/v2025/generic-approvals/bulk-cancel", {"approvalIds": [appr["id"]], "comment": "E2E: wrong assignee, cancelled"})
        raise SystemExit(f"FAIL: approval went to {assignees}, expected {a.approver}; cancelled it.")
    print(f"3. Approval {appr['id']} assigned to the chosen approver ({[x.get('name') for x in appr['assignedTo']]})")
    if a.before_decision:
        import os, subprocess
        subprocess.run(a.before_decision, shell=True, check=False, env={**os.environ, "IPID": ipid or "", "INC": inc})
    action = "approve" if a.scenario == "approve" else "reject"
    t.call("POST", f"/v2025/generic-approvals/{appr['id']}/{action}", {"comment": f"E2E {action} on behalf of the approver"})
    print(f"   {action}d on the approver's behalf")

    # 4. Outcome
    def finished():
        runs = t.call("GET", f"/v2025/workflows/{wf['id']}/executions?limit=5") or []
        run = next((r for r in runs if r.get("status") in ("Completed", "Failed") and r.get("startTime", "")[:19] >= launched_at), None)
        return run
    run = wait(finished, "the workflow run to finish", timeout=240)
    hist = t.call("GET", f"/v2025/workflow-executions/{run['id']}/history") or []
    done = [h["attributes"].get("stepName") for h in hist if h.get("type") == "ActivityTaskCompleted"]
    print(f"4. Workflow run {run['id']}: {run['status']}; steps completed: {done}")
    ok = run["status"] == "Completed"
    expected = "emailApproved" if a.scenario == "approve" else "emailDenied"
    ok &= expected in done
    if cfg.live and a.scenario == "approve":
        for person in people:
            def carrying():   # the status API lags the request by a few seconds
                rows = t.call("GET", f"/v3/access-request-status?requested-for={person}&limit=20") or []
                found = [r for r in rows if inc in ((r.get("requesterComment") or {}).get("comment") or "")]
                return found if len(found) >= len(items) else None
            try:
                hits = wait(carrying, f"requests for {person}", timeout=90)
            except SystemExit:
                hits = []
            print(f"   {person}: {len(hits)} request(s) carrying {inc}: {[(r.get('name'), r.get('state')) for r in hits]}")
            ok &= len(hits) == len(items)
    elif a.scenario == "approve":
        ok &= "requestAccess" not in done and "manageAccess" not in done
        print("   dry-run: confirmed nothing was requested")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (config_mod.ConfigError, TenantError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
