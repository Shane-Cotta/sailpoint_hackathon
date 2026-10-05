# Track 02: SaaS Connectivity

**The track** ([guide](https://developer.sailpoint.com/hack-day/saas-connectivity/)): build a cloud-hosted
connector in TypeScript that pulls accounts and entitlements from a throwaway demo app (the "SaaS
Connectivity Demo"), deploy it to an ISC tenant with the SailPoint CLI, then create a source and aggregate.
No virtual appliance is needed. The guide estimates about an hour.

**What we built:** `saas-connectivity-demo/` is a working SaaS connector. It supports `std:test-connection`,
`std:account:list`, `std:account:read`, `std:entitlement:list` and `std:entitlement:read`. It is deployed to
our tenant as connector `saas-connectivity-demo`, and source **"SaaS Connectivity Demo (Hack Day)"** is
aggregated: **50 accounts and 8 entitlements**, with group names resolved and `admin` marked privileged.

## Status: done (steps 1–10)
- Local: 13 unit tests pass, and every command works against the local dev server (`evidence/*.ndjson`).
- Cloud: `sail conn validate` passes 8 of 8 checks, and `sail conn invoke` returns 50 accounts and 8 groups.
- Tenant: Test Connection succeeds, the source is HEALTHY, and both aggregations completed (`evidence/isc-source.txt`).
- We did not do the step 11 stretch goals (provisioning, delta aggregation, email fan-out).
- We ran the step 10 UI steps through the API instead, so no clicks were needed. The demo web app
  (`di3u013yjgxuh.cloudfront.net`) is blocked by the sandbox firewall, so we created and seeded the demo key
  through the API (`POST /v1/keys`, then `POST /v1/seed`).

## Reproduce
```bash
cd saas-connectivity
# 1. demo key (valid 7 days) -> .env (gitignored)
API=https://dugfer5z7k.execute-api.us-east-1.amazonaws.com/v1
KEY=$(curl -s -X POST $API/keys | python3 -c 'import sys,json;print(json.load(sys.stdin)["apiKey"])')
curl -s -X POST -H "Authorization: Bearer $KEY" $API/seed            # 50 accounts, 8 groups
printf 'DEMO_API=%s\nDEMO_API_KEY=%s\n' $API $KEY > .env
printf '{"baseUrl":"%s","apiKey":"%s"}\n' $API $KEY > saas-connectivity-demo/config.json
# 2. build + test locally
cd saas-connectivity-demo && npm install && npm test
npm run build && npm run dev        # terminal 1: local server on :3000
../local-test.sh                    # terminal 2 (from saas-connectivity-demo/): smoke-test all commands
# 3. deploy (tenant PAT in SAIL_BASE_URL / SAIL_CLIENT_ID / SAIL_CLIENT_SECRET env vars)
npm run pack-zip
sail conn create "saas-connectivity-demo"     # first time only
sail conn upload -c saas-connectivity-demo -f dist/saas-connectivity-demo-0.1.0.zip
sail conn validate -c saas-connectivity-demo -p config.json -r
# 4. source + aggregation (instead of UI step 10)
cd .. && set -a && . ./.env && set +a
python3 isc_source.py create && python3 isc_source.py test
python3 isc_source.py aggregate && python3 isc_source.py status
python3 isc_source.py privileged                                   # mark 'admin' privileged
```
UI click-path for step 10: **Admin → Connections → Sources → Create New**, search "SaaS Connectivity Demo",
click **Configure**, then enter the name, owner, base URL and API key, then **Test Connection**. Next, run
**Entitlement Management → Entitlement Aggregation → Start Aggregation**, and after that **Account
Management → Account Aggregation → Start Aggregation**.

## How it ties into the main hack (manager team access review)
This source gives the review a realistic SaaS app with review-worthy data already in it:
- **A leaver who kept access:** 4 accounts are disabled (`active=false`). One of them, `gabriel.rossi`, still holds
  **admin**. That is the flag "disabled or leaver but still has privileged access".
- **Privileged access:** we marked `admin` as `privileged=true` in ISC. It has 9 holders, so the reviewer can
  compare each holder with their peers.
- **Stale access:** the `contractor` group is `status=deprecated` and has 3 holders (Andrei Popescu, Carmen
  Ruiz, Mike Mountain). That is the flag "deprecated entitlement still assigned".
- **Manager hierarchy:** each account carries a `manager` id. Five managers each have 9 reports, so you can
  build a team view straight from this source.
- Our MCP tools can read these accounts and entitlements through the normal ISC APIs (`/v3/accounts`,
  `/v3/entitlements`), and a certification campaign can be scoped to this source.

Files: `saas-connectivity-demo/` (connector), `local-test.sh`, `isc_source.py`, `evidence/`, `NOTES.md` (details).
