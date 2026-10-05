# SailPoint Hack Day: UI Plugins → UCSF Team Access Radar

**What this is.** This is our work for Hack Day **Track 03 "UI Plugins"** and the base for the scored main hack,
**"Extend UI Plugins"**. A UI plugin is a small web page that SailPoint Identity Security Cloud (ISC) shows *inside*
the product. It runs as the signed-in user, so it can call SailPoint APIs without a separate login.

**What we built: UCSF Team Access Radar.** (Everything we created in the shared tenant is prefixed *UCSF* so it stands out from other teams' resources.)

> *Before you rubber-stamp your quarterly access review, see which of your people have access their peers don't.*

Pick a manager and the page shows, inside ISC:
- **A summary:** team size, how many people are flagged, and how many flags are high, medium and low.
- **What needs a closer look:** each flag with its severity, the person, a plain-English reason, and the exact
  access items involved. For example: *Brandon.Mason (high): holds 2 privileged items, 1 of which no one else on the team has:
  Active Directory: AccountingGeneral*.
- **The team table**, with each person's access count and flag tags.
- **The access most of the team shares**, which is the baseline everyone else is compared with.
- **The manager's open certifications**, with progress and due date.
- **An Email manager button on every flag.** It starts a SailPoint workflow that emails the person's manager about that finding, then shows
  whether the email actually went out. In this demo tenant the email goes to the demo inbox, not the real manager.

**The same answer as our MCP server.** The plugin's flag rules (`src/app/team-access/team-flags.ts`) are a port of the
MCP server's `_team.py`. Both test suites run the same contract, `shared/team-flag-cases.json`, which is generated from the
Python reference. On live tenant data for three teams the two produced identical flags. So the chat assistant and the page
never disagree.

It started as the track's exercise, *Manager Reports Search*: a searchable manager dropdown and a table of reports, built on
SailPoint's official Angular starter (`manager-lookup-shcotta/`; the alias is kept so the registered plugin still works).

## Run it

**It's uploaded**, so just open it inside ISC (signed in as `hack.day`) and pick **Douglas.Flores**:

https://devrel-ga-25044.identitynow-demo.com/ui/plugin/0ac31b98-85df-4d2e-a6dd-7676f148a0ac

**To try local changes:** Run and Debug (⇧⌘D) → ▶ **Team Access Radar (UI plugin): dev server** (installs `node_modules` for your OS on
the first run, then serves https://localhost:4200; open that once and accept the certificate), then add `?spPluginDev=manager-lookup-shcotta`
to the URL above. Chrome may ask to allow local network access for the tenant.
Tests: ▶ **Team Access Radar (UI plugin): unit tests** (56 tests, including the 6 shared parity cases).

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

- **Working:** UCSF Team Access Radar page with the Email manager button, 56/56 unit tests, production build (only the expected bundle-size warning), and the
  live API calls (`POST /v3/search`, `GET /v3/certifications`) checked against the tenant.
- **In the tenant** (`devrel-ga-25044`): plugin instance `0ac31b98-…`, named **UCSF Team Access Radar**, private to `hack.day`,
  **uploaded** (bundle `b6d0e63d-…`) and also linked to the local dev server for development.
- **Email manager, and how it works:** the button starts *UCSF Flagged Report to Manager (Radar)* (`7326ad5b-…`) through the workflow
  **test** endpoint as the signed-in user. A browser plugin can't safely hold the external trigger's secret, which is how the MCP server's
  `notify_manager` starts its copy. Because of that, the Radar copy must stay **disabled**, and the button only works for users allowed to test
  workflows (`hack.day` is ORG_ADMIN). A production version would go through a small backend or a Launcher with a form.
- **Not done:** the nav-bar item is a UI-only step: Admin → Global → System Settings → Customize Navbar → add *UCSF Team Access Radar*.
- **Idea for next:** one-click revoke from the open certification.

More ideas and the engineering details are in [NOTES.md](NOTES.md).
