#!/usr/bin/env python3
"""Tiny stdlib-only ISC client for Hack Day Track 01 (Identity Workflows).

Reads SAIL_BASE_URL / SAIL_CLIENT_ID / SAIL_CLIENT_SECRET from ../.env (or the
environment). Never prints the secret or the access token.

Read-only commands:
  whoami                         token identity + scopes (decoded from the JWT claims)
  workflows [substr]             list workflows (id, enabled, name), optional name filter
  get-workflow <id|name>         dump one workflow as JSON
  executions <id|name>           list a workflow's executions
  history <execution-id>         execution history (what each step received/returned)
  find-identity <name-or-uid>    search identities (id, name, displayName, manager)
  actions [actionId]             workflow library actions (formFields for e.g. sp:send-email)

Write commands (only ever touch workflows this script created; ids kept in .state.json):
  create <file.json>             POST a new DISABLED workflow (refuses if the name exists)
  update <file.json>             PUT the definition to the workflow this script created with that name
  test <file.json|id> <identity-id> [identity-name]
                                 POST /test with an idn:identity-created payload, poll, print history
  enable <file.json|id> / disable <file.json|id>
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE = os.path.join(ROOT, ".state.json")  # names -> ids of workflows this script created (not secret)


def load_env():
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for k in ("SAIL_BASE_URL", "SAIL_CLIENT_ID", "SAIL_CLIENT_SECRET"):
        if not os.environ.get(k):
            sys.exit(f"missing {k} (put it in {path})")
    return os.environ["SAIL_BASE_URL"].rstrip("/")


BASE = None
_TOKEN = None


def token():
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": os.environ["SAIL_CLIENT_ID"],
        "client_secret": os.environ["SAIL_CLIENT_SECRET"],
    }).encode()
    req = urllib.request.Request(f"{BASE}/oauth/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _TOKEN = json.load(r)["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"token request failed: HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
    return _TOKEN


def call(method, path, body=None, ok=(200, 201, 202, 204)):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token()}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw[:500].decode(errors="replace")
        return e.code, payload


# The tenant may expose the new /workflows/v1 paths or only the versioned ones.
WF_PREFIXES = ["/workflows/v1", "/v2025/workflows", "/v3/workflows", "/beta/workflows"]
_WF = None


def wf_prefix():
    global _WF
    if _WF:
        return _WF
    for p in WF_PREFIXES:
        st, _ = call("GET", p + ("?limit=1" if p != "/workflows/v1" else ""))
        if st == 200:
            _WF = p
            return p
        print(f"  [{p} -> HTTP {st}]", file=sys.stderr)
    sys.exit("no workflows endpoint answered 200")


def exec_prefix():
    return {"/workflows/v1": "/workflow-executions/v1"}.get(wf_prefix(), wf_prefix().rsplit("/", 1)[0] + "/workflow-executions")


def library_prefix():
    return {"/workflows/v1": "/workflow-library/v1"}.get(wf_prefix(), wf_prefix().rsplit("/", 1)[0] + "/workflow-library")


def out(obj):
    print(json.dumps(obj, indent=2))


def state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(s):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=2)
        f.write("\n")


def list_workflows():
    st, body = call("GET", wf_prefix())
    if st != 200:
        sys.exit(f"list workflows: HTTP {st} {body}")
    return body


def resolve_wf(ref):
    """id, a workflow JSON file we created, or an exact/substring name."""
    if ref.endswith(".json") and os.path.exists(ref):
        name = json.load(open(ref))["name"]
        wid = state().get(name)
        if not wid:
            sys.exit(f"{name!r} was not created by this script (no id in .state.json)")
        return wid
    wfs = list_workflows()
    for w in wfs:
        if w["id"] == ref or w["name"] == ref:
            return w["id"]
    hits = [w for w in wfs if ref.lower() in w["name"].lower()]
    if len(hits) == 1:
        return hits[0]["id"]
    sys.exit(f"{len(hits)} workflows match {ref!r}: {[w['name'] for w in hits]}")


def owned_id(ref):
    """Write guard: only workflows recorded in .state.json (i.e. created here)."""
    wid = resolve_wf(ref)
    if wid not in state().values():
        sys.exit(f"refusing: workflow {wid} was not created by this script")
    return wid


def jwt_claims():
    part = token().split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def cmd_whoami():
    c = jwt_claims()
    keep = {k: c.get(k) for k in ("tenant_id", "pod", "org", "identity_id", "user_name", "client_id", "authorities", "scope", "exp")}
    out(keep)


def cmd_workflows(sub=""):
    for w in list_workflows():
        if sub.lower() in w["name"].lower():
            print(f"{w['id']}  enabled={str(w.get('enabled')).lower():5}  {w['name']}")


def cmd_get_workflow(ref):
    st, body = call("GET", f"{wf_prefix()}/{resolve_wf(ref)}")
    out(body)


def cmd_executions(ref):
    st, body = call("GET", f"{wf_prefix()}/{resolve_wf(ref)}/executions")
    if st != 200:
        sys.exit(f"HTTP {st} {body}")
    for e in body:
        print(f"{e.get('id')}  {e.get('status'):10}  start={e.get('startTime')}  close={e.get('closeTime')}")


def cmd_history(exec_id):
    st, body = call("GET", f"{exec_prefix()}/{exec_id}/history")
    out(body)
    return st, body


def cmd_find_identity(q):
    query = {"indices": ["identities"], "query": {"query": f'name:"{q}" OR displayName:"{q}"'},
             "includeNested": False, "queryResultFilter": {"includes": ["id", "name", "displayName", "email", "manager", "attributes.department", "attributes.jobTitle", "source", "accounts.source.name"]}}
    st, body = call("POST", "/v3/search?limit=20", query)
    if st != 200:
        sys.exit(f"search: HTTP {st} {body}")
    for i in body:
        srcs = sorted({(a.get("source") or {}).get("name", "") for a in i.get("accounts", [])})
        mgr = (i.get("manager") or {}).get("name")
        print(f"{i['id']}  {i.get('name'):22} {i.get('displayName')!s:22} manager={mgr!s:14} sources={srcs}")


def cmd_actions(action_id=None):
    path = f"{library_prefix()}/actions"
    if action_id:
        path += "?filters=" + urllib.parse.quote(f'id eq "{action_id}"')
    st, body = call("GET", path)
    if st != 200:
        sys.exit(f"HTTP {st} {body}")
    if action_id:
        out(body)
    else:
        for a in body:
            print(a.get("id"), "-", a.get("name"))


def cmd_create(path):
    wf = json.load(open(path))
    if any(w["name"] == wf["name"] for w in list_workflows()):
        sys.exit(f"a workflow named {wf['name']!r} already exists; use update")
    for r in wf["definition"]["steps"].get("Send Email", {}).get("attributes", {}).get("recipientEmailList", []) or []:
        if "REPLACE_WITH" in r:
            sys.exit("recipient is still the placeholder; rebuild with --recipient")
    body = dict(wf, enabled=False)
    if "owner" not in body:
        c = jwt_claims()
        if c.get("identity_id"):
            body["owner"] = {"type": "IDENTITY", "id": c["identity_id"], "name": c.get("user_name", "")}
    st, resp = call("POST", wf_prefix(), body)
    if st not in (200, 201):
        sys.exit(f"create: HTTP {st} {json.dumps(resp, indent=2)}")
    s = state()
    s[wf["name"]] = resp["id"]
    save_state(s)
    print(f"created {resp['id']}  {resp['name']}  enabled={resp.get('enabled')}")


def cmd_update(path):
    wf = json.load(open(path))
    wid = owned_id(path)
    st, cur = call("GET", f"{wf_prefix()}/{wid}")
    body = {k: wf[k] for k in ("name", "description", "definition", "trigger")}
    body["enabled"] = cur.get("enabled", False)
    if cur.get("owner"):
        body["owner"] = cur["owner"]
    st, resp = call("PUT", f"{wf_prefix()}/{wid}", body)
    print(f"update: HTTP {st}")
    if st != 200:
        out(resp)


def cmd_set_enabled(ref, enabled):
    wid = owned_id(ref)
    st, resp = call("PATCH", f"{wf_prefix()}/{wid}", [{"op": "replace", "path": "/enabled", "value": enabled}])
    print(f"enabled={enabled}: HTTP {st}")
    if st != 200:
        out(resp)


def cmd_test(ref, identity_id, identity_name=""):
    wid = owned_id(ref)
    # Same shape as the real idn:identity-created payload captured in the guide.
    payload = {"input": {
        "identity": {"id": identity_id, "name": identity_name, "type": "IDENTITY"},
        "attributes": {"displayName": identity_name},
    }}
    st, resp = call("POST", f"{wf_prefix()}/{wid}/test", payload)
    print(f"test: HTTP {st} {json.dumps(resp)}")
    if st not in (200, 201, 202):
        return
    exec_id = resp.get("workflowExecutionId") or resp.get("id")
    # The template's Wait step sleeps 1 minute before the lookups.
    for _ in range(30):
        time.sleep(10)
        st, ex = call("GET", f"{exec_prefix()}/{exec_id}")
        status = (ex or {}).get("status")
        print(f"  {time.strftime('%H:%M:%S')} execution {exec_id}: {status}")
        if status in ("Completed", "Failed", "Canceled", "Error"):
            break
    cmd_history(exec_id)


def main(argv):
    global BASE
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    BASE = load_env()
    cmd, args = argv[1], argv[2:]
    table = {
        "whoami": cmd_whoami, "workflows": cmd_workflows, "get-workflow": cmd_get_workflow,
        "executions": cmd_executions, "history": cmd_history, "find-identity": cmd_find_identity,
        "actions": cmd_actions, "create": cmd_create, "update": cmd_update, "test": cmd_test,
        "enable": lambda r: cmd_set_enabled(r, True), "disable": lambda r: cmd_set_enabled(r, False),
    }
    if cmd not in table:
        sys.exit(f"unknown command {cmd}")
    table[cmd](*args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
