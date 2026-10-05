# SailPoint Hack Day: UI Plugins

**What this is.** This is our work for Hack Day **Track 03 "UI Plugins"**, a guided mini hack of
about one hour. It is also the starting point for the scored main hack, **"Extend UI Plugins"**.
A UI plugin is a small web page that SailPoint Identity Security Cloud (ISC) shows *inside* the
product. It runs as the signed-in user, so it can call SailPoint APIs without a separate login.
We don't have to host anything: the SailPoint CLI uploads it to the tenant.

**What we built.** `manager-lookup-shcotta/` is the track's finished exercise, a
"Manager Reports Search" page. You pick a manager from a searchable dropdown and see a table of
their direct reports. All of it comes from one paginated SailPoint Identities API call. It is
built on SailPoint's official Angular starter, and it builds and passes its unit tests.

## Run it

```bash
cd ui-plugins/manager-lookup-shcotta
npx -y npm@11 install          # the template needs npm 11.12+
npm test -- --watch=false      # unit tests
npm run start:sandbox          # dev server on https://localhost:4200 (leave running)
```

To see it **inside ISC**, put the tenant PAT in `ui-plugins/.env` (copy `.env.example`), then run
these in a second terminal:

```bash
../sail.sh ui-plugins create --private   # register the plugin in the tenant (once)
../sail.sh ui-plugins link               # prints a ...?spPluginDev=... URL; open it in Chrome
```

When the sandbox is involved, also publish the port on the host Mac with
`sbx ports <sandbox-name> --publish 4200:4200`, and accept the self-signed certificate at
https://localhost:4200 once.

## How it gets into the tenant

The SailPoint CLI (`sail` 2.7.0) handles it. `npm run build` compiles the page, and
`../sail.sh ui-plugins upload` deploys it to the tenant's CDN. After that it is a real ISC page,
and you can add it to the top nav bar under Admin → Global → System Settings → Customize Navbar.

## Status

- Working: scaffold, `npm install`, production build, 40/40 unit tests, the dev server, and
  manifest validation.
- In the tenant (`devrel-ga-25044`): the plugin instance is registered, private to our user,
  and linked to the local dev server. Dev URL:
  https://devrel-ga-25044.identitynow-demo.com/ui/plugin/0ac31b98-85df-4d2e-a6dd-7676f148a0ac?spPluginDev=manager-lookup-shcotta
  (it needs the dev server running and port 4200 published).
- Not done yet: `upload` (the production deploy) and the nav-bar item.

## Recommended main-hack idea: "Team Access Radar"

> *Before you rubber-stamp your quarterly access review, see which of your people have access
> their peers don't.*

This is a page inside ISC for managers. It lists your direct reports and flags **unusual access**
(something few peers with the same role have) and **privileged access**. Next to that, it shows
the certifications and access requests waiting on you, riskiest first, with a one-click revoke.
It is the in-product companion to our MCP server, which answers the same questions in chat.
More ideas and the engineering details are in [NOTES.md](NOTES.md).
