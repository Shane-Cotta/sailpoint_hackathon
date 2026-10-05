# UI Plugins track: engineering notes

Source: https://developer.sailpoint.com/hack-day/ui-plugins (Track 03), plus the docs it links:
`/docs/ui-plugins`, `/docs/ui-plugins/prerequisites`, `/docs/ui-plugins/create-a-plugin-instance`,
`/docs/ui-plugins/cli-command-reference`, and `/hack-day/judging-criteria`.

## What the track is

- A UI plugin is a static web app (the starter is Angular 21 + PrimeNG) that ISC loads in a
  **sandboxed iframe** in a **slot** (the only documented slot is `full-page`). It gets the
  signed-in user's context and a **scoped API token** through a postMessage handshake with the
  ISC "App Shell", so API calls need no separate auth. You don't host anything yourself.
- The guided mini hack (about 1 hour) builds a "Manager Reports Search" page: one paginated
  `listIdentitiesV1` call. The manager dropdown and the direct-reports table are both built from
  `managerRef`.
- After that, a UI plugin can be the **main hack** entry. It is scored with the same rubric as
  the MCP track. To qualify it must use at least one SailPoint API/SDK and be demoable live in the
  tenant. The scored categories are Use-case clarity 25%, Creativity 20%, Functional execution 25%,
  API usage 10% (multiple API areas combined scores 5), and Coolness 20%.

## Architecture (how a plugin is built, loaded and deployed)

| Piece | What it does |
| --- | --- |
| `sp-ui-plugin.json` | `manifest` (alias, name, description, `apiScopes`, CSP/permission/iframe policies, `slots`) is sent to ISC. `build` (`outDir`, `port`) stays local. |
| `src/app/core/sailpoint-plugin.service.ts` | Runs the App Shell handshake once. Exposes `context()`, `status()`, `apiReady()`, `tenant()`, `user()` signals, plus `get()`/`post()` helpers that attach the token. |
| `src/app/app.config.ts` | `provideSailPoint()` (an HTTP interceptor that adds the token to `@sailpoint/angular-sdk` calls), the PrimeNG + SailPoint theme, and an app initializer that waits for the handshake. |
| `@sailpoint/angular-sdk/<area>` | Typed services for each API area (identities, search, certifications, access_request_approvals, iai_outliers, iai_peer_group_strategies, ...). They return Observables. `Paginator.paginate()` walks the pages. |
| Routing | Hash routing only (`withHashLocation()`). |
| Build | `ng build` with `baseHref`/`deployUrl` `./` (assets must be relative, because they are served from a CDN). |

Lifecycle, all through the SailPoint CLI `sail ui-plugins ...`:
1. `init` scaffolds from GitHub `sailpoint-oss/ui-plugin-templates` (`angular/starter`). It also
   validates the alias against the tenant.
2. `create [--private]` registers a plugin instance from the manifest. It needs right `idn:plugins-ui:create`.
3. `npm run start` starts an HTTPS dev server on :4200 with a self-signed cert. `link` then
   registers a per-developer override (`idn:plugins-ui:update`) and prints
   `https://<tenant>/ui/plugin/<id>?spPluginDev=<alias>`, which loads your localhost code inside
   ISC with a "Local Dev" badge. `create`/`link` also write CSP headers into `angular.json`, so
   restart the dev server after running them.
4. `npm run build` followed by `upload` deploys an immutable CDN bundle. `push-manifest` sends
   manifest changes (for example new `apiScopes`). `unlink`, `list`, `delete`, `enable` and
   `disable` are also available.
5. Optional nav item: Admin → Global → System Settings → Customize Navbar → Custom Item →
   Destination = Plugin. It needs the uploaded bundle, not a link.

Constraints: the UI Plugins feature flag must be on for the tenant. If it is off, you get
"Not enabled for this tenant" and need a developer advocate to turn it on. The user needs the
`idn:plugins-ui:{create,read,update,delete}` rights. The track expects Node 24+ and sail 2.7.0+.
API calls are limited to the declared `apiScopes` (the starter declares `sp:scopes:all`).
Supported browsers are Chrome, Edge and Firefox. Chrome may block the tenant from reaching
localhost. To fix it, open `chrome://settings/content/all`, find your tenant, and set
Local Network and Apps on Device to Allow.

## Setup that actually worked in this sandbox

Layout: `ui-plugins/manager-lookup-shcotta/` is the plugin workspace (alias `manager-lookup-shcotta`).

1. **SailPoint CLI 2.7.0**: the Linux arm64 tarball from GitHub releases. The checksum was
   verified against `sail_2.7.0_checksums.txt`, and the binary is installed at `~/.local/bin/sail`,
   which is already on PATH:
   ```bash
   curl -sSLO https://github.com/sailpoint-oss/sailpoint-cli/releases/download/2.7.0/sail_Linux_arm64.tar.gz
   tar xzf sail_Linux_arm64.tar.gz && cp sail ~/.local/bin/ && sail --version   # sail version 2.7.0
   ```
2. **Template**: `sail ui-plugins init` needs the tenant API to validate the alias, and that
   host was firewall-blocked, so I scaffolded by hand from
   `codeload.github.com/sailpoint-oss/ui-plugin-templates/tar.gz/refs/heads/main` (`angular/starter`).
   I then made the same edits `init` makes: `"starter"` becomes the alias in `package.json` and
   `angular.json` (including the `starter:build:*` targets), `signal('starter')` in `app.ts`,
   and the manifest alias, name, description and `build.outDir`.
   `sail ui-plugins validate-manifest` reports: *Manifest structure is valid (offline check only).*
3. **npm**: the template needs **npm >= 11.12**. The sandbox's npm 9 (and every npm bundled with
   Node 22) fails with `Cannot read properties of null (reading 'edgesOut')`. Node 22.22 itself
   is fine for Angular 21. Use npm 11 through npx:
   ```bash
   cd manager-lookup-shcotta && npx -y npm@11 install     # 477 packages, 0 vulnerabilities
   ```
4. **Build**: `npm run build` produces `dist/manager-lookup-shcotta/browser` with relative asset
   URLs. The "bundle initial exceeded maximum budget" warning is expected (about 223 kB transfer).
5. **Tests**: `npx ng test --watch=false` passes 40 of 40. The tutorial's code breaks the starter's
   `app.spec.ts`, which checks the old heading, so I rewrote it to test manager de-duplication
   and sorting, the reports filter, and the helper functions.
6. **Dev server**: `npm run start:sandbox` runs `ng serve --ssl --host 0.0.0.0`. I checked it over
   https on localhost:4200 and on eth0, and both returned HTTP 200. Use `start:sandbox` here
   because plain `npm start` binds only to localhost.
7. **CLI auth**: the CLI's keyring does not work in the sandbox. It warns: *"PAT will only work
   with environment variables"*. `./sail.sh` loads `ui-plugins/.env` (gitignored, holding
   `SAIL_BASE_URL`, `SAIL_CLIENT_ID` and `SAIL_CLIENT_SECRET`) and runs `sail` with stdin set to
   `/dev/null`. Never run bare `sail env show`/`sail env` here: they loop on "Press Enter to
   continue" forever.

## Run / build / deploy

```bash
cd ui-plugins/manager-lookup-shcotta
npx -y npm@11 install
npm run start:sandbox          # terminal 1, leave running (https://localhost:4200)
../sail.sh ui-plugins list     # terminal 2: checks credentials, feature flag and rights
../sail.sh ui-plugins create --private
../sail.sh ui-plugins link     # prints https://devrel-ga-25044.identitynow-demo.com/ui/plugin/<id>?spPluginDev=manager-lookup-shcotta
# restart start:sandbox after create/link (they rewrite angular.json headers)
npm run build && ../sail.sh ui-plugins upload   # deploy; then optionally add the Navbar item
../sail.sh ui-plugins unlink   # when done with local dev
```

On the host Mac: `sbx ports <sandbox-name> --publish 4200:4200` (run `hostname` inside the sandbox
to get the name). Then open https://localhost:4200 once in the browser and accept the self-signed
cert before you open the `?spPluginDev=` URL. ISC tells the browser to load `https://localhost:<port>`,
so the host port must equal the linked port.

## Tenant status (verified 2026-10-05 once the firewall approval landed)

- `../sail.sh ui-plugins list` returned *No plugin instances found.*, which means the token,
  the UI Plugins feature flag and `idn:plugins-ui:read` are all fine. The PAT identity is
  `hack.day`, which has `ORG_ADMIN`.
- `create --private` returned *Created plugin instance 0ac31b98-85df-4d2e-a6dd-7676f148a0ac
  (alias: manager-lookup-shcotta)*. The instance is restricted to the PAT owner's identity
  (`aad245a6...`).
- `link` returned *Plugin manager-lookup-shcotta linked to port 4200*. Dev URL:
  https://devrel-ga-25044.identitynow-demo.com/ui/plugin/0ac31b98-85df-4d2e-a6dd-7676f148a0ac?spPluginDev=manager-lookup-shcotta
- `create` wrote the CSP and Permissions-Policy dev headers into `angular.json`. The CSP sets
  `connect-src 'self' https://devrel-ga-25044.api.identitynow-demo.com`. After a restart,
  `start:sandbox` serves them, which I checked with `curl -I`.
- Tenant data: 308 identities, 298 of which have a manager, across 52 distinct managers. The
  biggest teams have 19, 19 and 18 reports. That is enough for a realistic manager-lookup demo.
- **Not done (left for the user):** `upload` (the deploy step) and the Navbar item.

### CLI gotchas found along the way
- `link` needs a tenant **UI** URL, and environment variables can't provide one. I added a
  credential-free environment to `~/.sailpoint/config.yaml`:
  ```yaml
  environments:
    default:
      tenanturl: https://devrel-ga-25044.identitynow-demo.com
      baseurl: https://devrel-ga-25044.api.identitynow-demo.com
  ```
- Running `sail ... --debug` once **saves `debug: true` to the config file**. After that, every
  command dumps HTTP requests, including the `Authorization: Bearer` header. I reset it to
  `debug: false`. Don't use `--debug` when the output might be shared.
- Python `urllib` calls to the tenant API return 403 from Cloudflare unless you set a
  `User-Agent` header. `curl` and the CLI work without one.

## Open items

- User, on the host: `sbx ports <sandbox-name> --publish 4200:4200` (sandbox name = `hostname` output: herdr-claude-code-f8b0d59fde8f), then start
  `npm run start:sandbox` in the sandbox. Open https://localhost:4200 and accept the
  self-signed cert, then open the dev URL above in Chrome, Edge or Firefox. If Chrome blocks
  loopback, set Local Network and Apps on Device to Allow for the tenant domain.
- Firewall: `devrel-ga-25044.api.identitynow-demo.com` is now reachable from the sandbox.
  `devrel-ga-25044.identitynow-demo.com` (the UI host) is only opened by the user's own browser,
  so the sandbox doesn't need it. `sail ui-plugins init` would also fetch the template from
  GitHub (`raw.githubusercontent.com`/`api.github.com`). Scaffolding through codeload avoids that.

## Plugin ideas (complementing the MCP "manager team access review" track)

The plugin runs **as the signed-in manager**, so "my team" is just `context().user.id`. Calls
like pending approvals and active certifications are already scoped to that user. The MCP
server answers these questions in chat. The plugin shows the same insight inside ISC, where the
manager acts on it. Both should share one scoring rule (peer prevalence) so that the answers match.

1. **Team Access Radar (recommended).** A full-page "My team" dashboard. It shows each direct report
   (Search `identities` with `manager.id:<me>`) with badges for **outlier access** (an entitlement or
   role that fewer than 20% of peers with the same department or job title hold), **privileged**
   items (`access[].privileged`), and IAI outlier score (`iai_outliers`). A side panel lists the
   manager's **pending work**: active certifications (`certifications`) and pending approvals
   (`access_request_approvals`), sorted by how risky the identities in them are. A click on
   "Revoke" files a revoke access request (`access_requests`). This combines several API areas,
   which scores well under API usage. Use-case in one sentence: *"Before you rubber-stamp your
   quarterly review, see which of your people have access their peers don't."*
2. **Peer-diff heatmap.** A grid of reports by access items, with each cell coloured by how common
   that access is among peers (`search` aggregations). Rare access stands out visually, which makes
   a good demo. A drill-down shows when the access was granted (`identity_history`).
3. **Certification triage view.** For each open certification the manager owns, it re-sorts the
   review items so outlier or privileged access comes first and "everyone in the department has
   this" comes last. Each row links to the native cert page to make the decision. It complements
   the MCP "pending certifications" tool directly.
4. **Mover drift detector.** It finds reports whose department or title changed recently
   (`identity_history`) but who still hold their previous department's access. It suggests
   revocations and can start a Workflow through the Launchers API, as in the starter's Workflows tab.
