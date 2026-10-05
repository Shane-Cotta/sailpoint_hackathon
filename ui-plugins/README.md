# SailPoint Hack Day: UI Plugins → Team Access Radar

**What this is.** This is our work for Hack Day **Track 03 "UI Plugins"** and the base for the scored main hack,
**"Extend UI Plugins"**. A UI plugin is a small web page that SailPoint Identity Security Cloud (ISC) shows *inside*
the product. It runs as the signed-in user, so it can call SailPoint APIs without a separate login.

**What we built: Team Access Radar.**

> *Before you rubber-stamp your quarterly access review, see which of your people have access their peers don't.*

Pick a manager and the page shows, inside ISC:
- **A summary:** team size, how many people are flagged, and how many flags are high, medium and low.
- **What needs a closer look:** each flag with its severity, the person, a plain-English reason, and the exact
  access items involved. For example: *Brandon.Mason (high): holds 2 privileged items, 1 of which no one else on the team has:
  Active Directory: AccountingGeneral*.
- **The team table**, with each person's access count and flag tags.
- **The access most of the team shares**, which is the baseline everyone else is compared with.
- **The manager's open certifications**, with progress and due date.

**The same answer as our MCP server.** The plugin's flag rules (`src/app/team-access/team-flags.ts`) are a port of the
MCP server's `_team.py`. Both test suites run the same contract, `shared/team-flag-cases.json`, which is generated from the
Python reference. On live tenant data for three teams the two produced identical flags. So the chat assistant and the page
never disagree.

It started as the track's exercise, *Manager Reports Search*: a searchable manager dropdown and a table of reports, built on
SailPoint's official Angular starter (`manager-lookup-shcotta/`; the alias is kept so the registered plugin still works).

## Run it

**From VS Code:** Run and Debug (⇧⌘D) → ▶ **Team Access Radar (UI plugin): dev server**. The first run installs
`node_modules` for your OS, then serves https://localhost:4200. Open that once and accept the self-signed certificate, then open
the plugin inside ISC (signed in as `hack.day`):

https://devrel-ga-25044.identitynow-demo.com/ui/plugin/0ac31b98-85df-4d2e-a6dd-7676f148a0ac?spPluginDev=manager-lookup-shcotta

Pick **Douglas.Flores**. Chrome may ask to allow local network access for the tenant.
Tests: ▶ **Team Access Radar (UI plugin): unit tests** (51 tests, including the 6 shared parity cases).

From a terminal instead:
```bash
cd ui-plugins/manager-lookup-shcotta
npx -y npm@11 install          # the template needs npm 11.12+
npx ng test --watch=false      # unit tests
npm start                      # dev server on https://localhost:4200
```
The plugin is already registered and linked in the tenant. To redo that: `../sail.sh ui-plugins create --private`, then
`../sail.sh ui-plugins link`. `sail.sh` reads the PAT from the gitignored `ui-plugins/.env`.

## How it gets into the tenant

The SailPoint CLI (`sail` 2.7.0) handles it. `npm run build` compiles the page, and `../sail.sh ui-plugins upload` deploys it
to the tenant's CDN. After that it is a real ISC page without a dev server, and you can add it to the top nav bar under
Admin → Global → System Settings → Customize Navbar. Manifest-only changes (name, scopes) go up with `../sail.sh ui-plugins push-manifest`.

## Status

- **Working:** Team Access Radar page, 51/51 unit tests, production build (only the expected bundle-size warning), and the
  live API calls (`POST /v3/search`, `GET /v3/certifications`) checked against the tenant.
- **In the tenant** (`devrel-ga-25044`): plugin instance `0ac31b98-…`, renamed **Team Access Radar** (manifest pushed),
  private to `hack.day`, and linked to the local dev server.
- **Not done yet:** `upload` (the production deploy, so it works without the dev server) and the nav-bar item.
- **Ideas for next:** a "Notify manager" button through a Launcher/workflow (the MCP server already does this with
  `notify_manager`), and one-click revoke from the open certification.

More ideas and the engineering details are in [NOTES.md](NOTES.md).
