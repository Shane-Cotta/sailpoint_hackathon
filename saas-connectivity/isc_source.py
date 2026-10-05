#!/usr/bin/env python3
"""Step 10 of the track (create source + aggregate) done through the ISC API instead of the UI.

Reads tenant creds (SAIL_BASE_URL / SAIL_CLIENT_ID / SAIL_CLIENT_SECRET) and the demo key
(DEMO_API / DEMO_API_KEY) from the environment. Never prints secrets.

    python3 isc_source.py info         # show the uploaded connector + any existing source
    python3 isc_source.py create       # create the source if missing (idempotent)
    python3 isc_source.py test         # Test Connection
    python3 isc_source.py aggregate    # entitlements first, then accounts
    python3 isc_source.py status       # counts of accounts / entitlements landed in ISC
    python3 isc_source.py privileged   # mark the demo 'admin' entitlement privileged (review flag)
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE_NAME = os.environ.get("SOURCE_NAME", "SaaS Connectivity Demo (Hack Day)")
CONNECTOR_NAME = os.environ.get("CONNECTOR_NAME", "SaaS Connectivity Demo")  # "name" in connector-spec.json
BASE = os.environ["SAIL_BASE_URL"].rstrip("/")
# Cloudflare in front of the tenant rejects the default "Python-urllib" User-Agent (error 1010).
UA = {"User-Agent": "hackday-saas-connectivity/1.0"}


def token() -> str:
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": os.environ["SAIL_CLIENT_ID"],
        "client_secret": os.environ["SAIL_CLIENT_SECRET"],
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{BASE}/oauth/token", data=data, headers=UA)) as r:
        return json.load(r)["access_token"]


TOKEN = token()


def call(method: str, path: str, body=None, ctype="application/json"):
    data = None
    if body is not None:
        data = json.dumps(body).encode() if ctype.endswith("json") else body
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=UA)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode(errors="replace")


def jwt_identity() -> str:
    payload = TOKEN.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["identity_id"]


def connector():
    # An uploaded SaaS connector shows up in /v3/connectors as "<spec name> (tag: latest)" with a
    # UUID scriptName, which is what a source's "connector" field must reference.
    q = urllib.parse.quote(f'name sw "{CONNECTOR_NAME}"')
    st, items = call("GET", f"/v3/connectors?limit=250&filters={q}")
    matches = [c for c in items or [] if c.get("name") == f"{CONNECTOR_NAME} (tag: latest)"]
    if len(matches) != 1:
        sys.exit(f"expected one '{CONNECTOR_NAME} (tag: latest)' connector, found {len(matches)} (HTTP {st})")
    return matches[0]


def source():
    q = urllib.parse.quote(f'name eq "{SOURCE_NAME}"')
    st, items = call("GET", f"/v3/sources?filters={q}")
    return items[0] if st == 200 and items else None


def cmd_info():
    c = connector()
    print(json.dumps({k: c.get(k) for k in ("name", "type", "scriptName", "className", "status")}, indent=2))
    s = source()
    print("source:", s and {k: s.get(k) for k in ("id", "name", "connector", "status")})


def cmd_create():
    s = source()
    if s:
        print("source already exists:", s["id"])
        return
    c = connector()
    # Gotcha: POST /v3/sources with connectorAttributes (or a description) in the body returns a bare
    # "400.1 Bad request content" for this SaaS connector. A minimal POST works, then PATCH the config in.
    body = {
        "name": SOURCE_NAME,
        "owner": {"type": "IDENTITY", "id": jwt_identity()},
        "connector": c["scriptName"],
    }
    st, out = call("POST", "/v3/sources", body)
    print("create source HTTP", st)
    if st >= 300:
        print(json.dumps(out, indent=2)[:2000])
        sys.exit(1)
    print({k: out.get(k) for k in ("id", "name", "connector", "status")})
    ops = [
        {"op": "add", "path": "/connectorAttributes/baseUrl", "value": os.environ["DEMO_API"]},
        {"op": "add", "path": "/connectorAttributes/apiKey", "value": os.environ["DEMO_API_KEY"]},
        {"op": "replace", "path": "/description",
         "value": "Hack Day Track 02: cloud-hosted SaaS connector for the SaaS Connectivity Demo app"},
    ]
    st, _ = call("PATCH", f"/v3/sources/{out['id']}", ops, ctype="application/json-patch+json")
    print("patch source config HTTP", st)


def need_source():
    s = source()
    if not s:
        sys.exit("source not found; run create first")
    return s


def cmd_test():
    s = need_source()
    st, out = call("POST", f"/beta/sources/{s['id']}/connector/test-configuration", {})
    print("test-configuration HTTP", st, json.dumps(out)[:600])


def cmd_aggregate():
    s = need_source()
    # Entitlements first so accounts' groups resolve to names.
    st, out = call("POST", f"/beta/entitlements/aggregate/sources/{s['id']}", b"", ctype="multipart/form-data; boundary=x")
    print("entitlement aggregation HTTP", st, json.dumps(out)[:400])
    time.sleep(20)
    boundary = "----hackday"
    form = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"disableOptimization\"\r\n\r\ntrue\r\n"
            f"--{boundary}--\r\n").encode()
    st, out = call("POST", f"/beta/sources/{s['id']}/load-accounts", form,
                   ctype=f"multipart/form-data; boundary={boundary}")
    print("account aggregation HTTP", st, json.dumps(out)[:400])


def count(path: str) -> str:
    st, items = call("GET", path)
    return f"{len(items)}" if st == 200 else f"HTTP {st}"


def cmd_status():
    s = need_source()
    sid = s["id"]
    q = urllib.parse.quote(f'source.id eq "{sid}"')
    print("accounts:", count(f"/v3/accounts?limit=250&filters=sourceId%20eq%20%22{sid}%22"))
    st, ents = call("GET", f"/v3/entitlements?limit=250&filters={q}")
    if st != 200:
        st, ents = call("GET", f"/beta/entitlements?limit=250&filters={q}")
    if st == 200:
        print("entitlements:", len(ents))
        for e in ents:
            print(f"  {e.get('name') or e.get('value'):<22} privileged={e.get('privileged')}")
    else:
        print("entitlements: HTTP", st, str(ents)[:300])


def cmd_privileged():
    s = need_source()
    q = urllib.parse.quote(f'source.id eq "{s["id"]}"')
    st, ents = call("GET", f"/beta/entitlements?limit=250&filters={q}")
    for e in ents or []:
        if e.get("value") and e.get("name") in ("admin", "Administrator"):
            st2, out = call("PATCH", f"/beta/entitlements/{e['id']}",
                            [{"op": "replace", "path": "/privileged", "value": True}],
                            ctype="application/json-patch+json")
            print("mark privileged", e.get("name"), "HTTP", st2)


if __name__ == "__main__":
    {"info": cmd_info, "create": cmd_create, "test": cmd_test, "aggregate": cmd_aggregate,
     "status": cmd_status, "privileged": cmd_privileged}[sys.argv[1] if len(sys.argv) > 1 else "info"]()
