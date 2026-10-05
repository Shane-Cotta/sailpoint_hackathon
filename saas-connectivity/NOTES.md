# Track 02 engineering notes

Guide: https://developer.sailpoint.com/hack-day/saas-connectivity/ (the URL needs the trailing slash; without it you get a 301).
Run date: 2026-10-05. Tenant: `devrel-ga-25044` (shared demo tenant, PAT user `hack.day`, ORG_ADMIN).

## What exists in the tenant (created by this track)
| Object | Id / name |
|---|---|
| Connector (alias) | `saas-connectivity-demo`, id `3dd9a454-9627-4e5f-8c9e-10daaf9e00f5`, version 2 (tag `latest`) |
| Connector as seen by `/v3/connectors` | name `SaaS Connectivity Demo (tag: latest)`, scriptName/type `a99fcdeb-2667-4ec9-9a20-f99588f9046a` |
| Source | `SaaS Connectivity Demo (Hack Day)`, id `796ddbe4f7844c01a6d43f0cb39b85d4`, owner `hack.day` |
| Aggregated | 50 accounts, 8 entitlements; `admin` entitlement set `privileged=true` |
| Side effect | Each uncorrelated account got its own identity (for example "Gabriel Rossi"), so the tenant has about 50 new identities |

Cleanup, if anyone wants it: delete the source in the UI (Admin → Connections → Sources → the source → Delete),
then run `sail conn delete -c saas-connectivity-demo`. We have not done either.

## Demo system
- API base: `https://dugfer5z7k.execute-api.us-east-1.amazonaws.com/v1`. Overview: `GET https://dugfer5z7k.execute-api.us-east-1.amazonaws.com/`.
- The web app (`https://di3u013yjgxuh.cloudfront.net/welcome`) and the OpenAPI file
  (`https://di3u013yjgxuh.cloudfront.net/openapi/saas-connectivity-demo.yaml`) are **blocked by the sandbox
  firewall** ("Approval required for di3u013yjgxuh.cloudfront.net"). We did not need them:
  - `POST /v1/keys` (no auth) returns `{apiKey: "sck_...", expiresAt, readOnly:false}`. The key lasts 7 days (it expires 2026-10-12).
  - `POST /v1/seed` (Bearer key) returns `{"seeded":true,"accounts":50,"entitlements":8}`. This is the web app's "Seed data" button.
  - Other endpoints we used: `GET /health`, `GET /users?limit&cursor&include=email`, `GET /users/{id}`,
    `GET /users/{id}/emails`, `GET /groups?limit&includePermissions=true`, and `GET /groups/{id}`. Unknown ids return 404.
- The key is stored only in `saas-connectivity/.env` and `saas-connectivity-demo/config.json`. Both files are
  gitignored and chmod 600.

## SailPoint CLI setup
- The guide says to use CLI 2.4.0 or later. We downloaded the latest release, **2.7.0**, as the arm64 `.deb` (the sandbox is aarch64):
  `curl -sSLO https://github.com/sailpoint-oss/sailpoint-cli/releases/download/2.7.0/sail_2.7.0_linux_arm64.deb`,
  then ran `dpkg-deb -x` and copied `usr/bin/sail` to `~/.local/bin/sail`. Another agent had already put the
  same binary there. `api.github.com` returns 401 through the proxy, but direct release-asset URLs work.
- **`sail set pat` cannot work in this sandbox**, because the CLI warns "Secrets storage is not currently
  functional on this platform, PAT will only work with environment variables". We authenticated with
  environment variables only: `SAIL_BASE_URL`, `SAIL_CLIENT_ID` and `SAIL_CLIENT_SECRET`, sourced from
  `python-mcp-server-template/.env`. `sail env create` and `sail set auth pat` are not needed this way.
- `~/.sailpoint/config.yaml` is shared with other agents' sessions, so we ran every `sail` command with
  `HOME=<scratch>/sailhome` to keep our config separate. Also use `< /dev/null` with `sail`, because it can
  hang waiting on a prompt (another agent's `sail env show` was stuck at 100% CPU).

## Steps done, compared with the guide
1. Prereqs: Node 22 and sail 2.7.0 (see above). We skipped Postman.
2. Demo system: we used the API, because the web app is blocked (see above).
3. `sail conn init "saas-connectivity-demo"` then `npm install`. The scaffold contains `connector-spec.json`,
   `src/index.ts`, `src/my-client.ts`, two `*.spec.ts` files, and `package.json` (`@sailpoint/connector-sdk`
   1.2.7, `spcx` dev server, `ncc` build).
4. `connector-spec.json` is copied verbatim from the guide.
5–8. We implemented `MyClient` (testConnection, getAllAccounts with a cursor loop, getAccount with 404 →
   `ConnectorErrorType.NotFound`, getAllEntitlements, getEntitlement) and the handlers in `src/index.ts`.
9. `npm run pack-zip`, `sail conn create`, `sail conn upload` and `sail conn invoke ... -p config.json`, then
   `sail conn validate -r` (8 of 8 checks pass; see `evidence/cloud-validate.txt`).
10. We created the source and ran both aggregations **through the API** with `isc_source.py`, not the UI.

### Deviations and fixes (worth reading)
- **Bug in the guide's step 8 recap:** it adds `key: SimpleKey(entitlement.id)` alongside `identity`/`uuid`.
  With that line, `sail conn invoke` and `sail conn validate` both pass, but the **ISC entitlement aggregation
  fails** with `[ConnectorError] invalid output format: Schema validation error in path: [{$ref ref_mismatch
  Value does not match the reference schema map[]}]`. Account aggregation still works, and ISC then creates
  only 7 entitlements, named by their raw `grp_...` ids. Removing `key` (upload v2) fixed it: 8 entitlements
  now carry their proper names.
- **The guide's spec declares `std:entitlement:read`, but the guide never implements it.** We implemented it
  (`GET /groups/{id}`). `sail conn validate` calls it with a **compound** key
  (`{compound:{lookupId,uniqueId}}`), so the handler falls back to `input.identity` when the key isn't `simple`.
  The `std:entitlement:read` output type has no `deleted` field, so the read handler removes it from the
  shared mapper's output.
- The guide's mapping table says to map "every attribute you declared". Its recap code maps only 9 of the 16.
  We map all 16 (`manager`, `employeeId`, `location`, `costCenter`, `phone`, `active`, `locked`, and the rest),
  plus `disabled: !active` and `locked`.
- The scaffold's unit tests target the mock client. We rewrote them with a stubbed
  `createConnectorHttpClient`, so they make no network calls. There are 13 tests, and they cover the paging,
  401 and 404 paths. Two extra branch tests were needed to meet the scaffold's 50% branch-coverage threshold.
- `npm run dev` runs `spcx run dist/index.js` and starts `tsc --watch`. Run `npm run build` once first.
  `npm run pack-zip` runs `npm ci`, which deletes `node_modules`, so stop the dev server before packing.

### Creating the source via API (gotchas, all handled in `isc_source.py`)
- Cloudflare in front of the tenant returns **403 "error code: 1010"** to Python's default
  `Python-urllib/x` User-Agent. Set any custom User-Agent.
- In `/v3/connectors`, the uploaded connector appears as `"<spec name> (tag: latest)"`, and its
  `scriptName` is a UUID that differs from the CLI's connector id. The source's `connector` field must be
  that scriptName.
- `POST /v3/sources` with `connectorAttributes` (baseUrl and apiKey) or `description` in the body returns a
  bare `400.1 Bad request content` with no causes. A **minimal body** (`name`, `owner`, `connector`) returns
  201. After that, `PATCH /v3/sources/{id}` (json-patch) adds `/connectorAttributes/baseUrl`,
  `/connectorAttributes/apiKey` and `/description`.
- Test Connection: `POST /beta/sources/{id}/connector/test-configuration` returns `SUCCESS`.
- Entitlement aggregation: `POST /beta/entitlements/aggregate/sources/{id}` returns 202. Track the task with
  `GET /beta/task-status/{taskId}`.
- Account aggregation: `POST /beta/sources/{id}/load-accounts` (multipart) works. `/v3/sources/{id}/load-accounts`
  returns 404, because the router rewrites it to `/v3/sources/sources/...`.
- Marking an entitlement privileged: `PATCH /beta/entitlements/{id}` with `[{op:replace,path:/privileged,value:true}]`.

## Firewall hosts
- Blocked (approval needed if you want them): `di3u013yjgxuh.cloudfront.net` (demo web app and OpenAPI).
- Worked: `registry.npmjs.org`, `github.com` release downloads, the demo API host, `developer.sailpoint.com`,
  and the tenant API `devrel-ga-25044.api.identitynow-demo.com`. `api.github.com` returns 401.

## Data highlights (for the main hack)
- Disabled accounts: liam.kavanagh, diego.alvarez, **gabriel.rossi (user and admin)**, and peter.vandenberg.
- Holders of `admin` (privileged): brenda.cooper, helena.bergstrom, colin.murphy, alan.bradley, owen.ocean,
  fred.mcbread, carmen.ruiz, gabriel.rossi and sarah.sky.
- Holders of `contractor`, which is deprecated: andrei.popescu, carmen.ruiz and mike.mountain.
- Managers: sarah.sky, owen.ocean, brenda.cooper, alan.bradley and fred.mcbread each have 9 reports; 5 accounts have no manager.
- The demo API also supports writes and provisioning (create, update, enable, disable, unlock), a `readOnly`
  key mode, and an `updatedSince` filter for delta aggregation. These are the stretch goals we left undone.
