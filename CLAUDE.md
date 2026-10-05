# SailPoint Hack Day (Navigate 2026) — workspace guide

Hub: https://developer.sailpoint.com/hack-day. **Only the main hack is judged**: either *MCP Server* or
*Extend UI Plugins*. The three mini hacks (Identity Workflows, SaaS Connectivity, UI Plugins) are guided
and take about one hour each. Judging rubric: use case 25%, execution 25%, creativity 20%, coolness 20%,
API usage 10%; needs at least one SailPoint API and a live demo. Our theme throughout is **manager team access review**: help a manager see
their direct reports' access, flag what's risky or unusual, and act on pending reviews.

## Layout: one repo, merged
The repo is rooted at `python-mcp-server-template/` (`main`). The three track branches were built in parallel worktrees and then
**merged into `main` (octopus merge `12e3ad1`)**. Each track lives in its own top-level folder:

| Track | Folder in the repo | Status file |
|---|---|---|
| Main hack: MCP Server (judged) | repo root (`src/sailpoint_mcp/tools/`) | `README.md` (Hack Day section) |
| Mini 01: Identity Workflows | `identity-workflows/` | `README.md`, `NOTES.md` |
| Mini 02: SaaS Connectivity | `saas-connectivity/` | `README.md`, `NOTES.md` |
| Mini 03 / main-hack option: UI Plugins | `ui-plugins/` | `README.md`, `NOTES.md` |

**Work on `main`.** The per-track worktrees were removed after the merge; their gitignored config files (`.env`, the connector's `config.json`) were copied into the matching folders on `main`. The track branches still exist and are fully merged.
If you need parallel agents again, create fresh worktrees from `main` and keep the same rule: one folder per track.

Rules for every track:
- Never edit the template files from a track branch. Stay inside the track's subfolder.
- Each track keeps a **human-readable `README.md`** (about one screen: what, how to run, status, how it ties
  to the theme) and an engineering `NOTES.md`. The workspace `README.md` indexes all of them, so update it when a track's status changes.
- Don't push, and don't merge future branches, without asking.
- Commit messages end with the Co-Authored-By line given in the session's system reminder.
- **Keep `AGENT-WORKFLOW.md` current**: add to its tables, diagrams and changelog whenever an agent is started, finishes,
  or coordination changes. Keep `RUNBOOK.md` current whenever how to run, demo or clean up changes.

## Tenant & credentials
- Demo tenant `devrel-ga-25044`. UI: https://devrel-ga-25044.identitynow-demo.com, API: https://devrel-ga-25044.api.identitynow-demo.com
- PAT (client credentials) in `python-mcp-server-template/.env` (gitignored, mode 600). Copy it into a track's gitignored `.env`
  when needed. **Never print or commit the secret.** UI login credentials are not stored anywhere; don't ask for them in files.
- Shared tenant: create what a track needs, but don't modify or delete objects we didn't create.
- **Prefix everything we create in the tenant with `UCSF`** (the user asked, so other teams can tell our resources apart). Scripts that look things up by name
  (`identity-workflows/.state.json`, `saas-connectivity/isc_source.py`, `scripts/create_demo_campaign.py`) already use the UCSF names.

## Running it (the user works in VS Code on the Mac; the folder is shared with the sandbox)
- The launcher `python-mcp-server-template/scripts/run-server.sh` (with `scripts/env.sh`) uses a per-OS venv: `.venv` on Linux,
  `.venv-mac` on macOS, via `uv run --extra dev`. **Every client config points at it**: `.vscode/mcp.json` (VS Code native MCP),
  `.mcp.json` (Claude Code, at the root and in the repo), and the Inspector task. Don't point any config at a specific venv's python.
- **The user runs everything from the Run and Debug ▶ dropdown** (`.vscode/launch.json`), not from tasks (there is no tasks.json):
  grouped Setup (install env, unit tests, tenant connection), Demo 1–4 plus "create demo campaign", Tools (call any tool,
  Inspector, attach to the `sailpoint-debug` server on 127.0.0.1:5678), and Other tracks (UI plugin dev server, connector tests).
  Python entries pin `.venv-mac/bin/python`; Node entries install `node_modules` per OS (`node_modules/.installed-<OS>` marker).
  New runnable things go in that dropdown.
- `node_modules` in the UI-plugin and connector folders were installed in the sandbox (Linux). Reinstall before running them on the Mac.
- Full steps: `RUNBOOK.md`.

## Track facts worth knowing
- UI Plugins: Angular + PrimeNG, needs **npm 11.12+** (`npx -y npm@11 install`). The `sail` CLI 2.7.0 is at `~/.local/bin/sail`;
  run it through `ui-plugins/sail.sh`, which loads the PAT from a gitignored `.env`. Plugin instance `0ac31b98-85df-4d2e-a6dd-7676f148a0ac`
  is registered (private) and linked to port 4200. **Never run `sail` with `--debug`**: it saves the setting and prints access tokens.
- SaaS Connectivity uses the disposable demo app at `di3u013yjgxuh.cloudfront.net`. Its API key expires 7 days after it was created.
- Identity Workflows: workflows `499d37f2-…` and `4f178d1b-…` are created but disabled. The recipient is `shane.cotta+hackday@gmail.com` (Shane's plus-address for the demo).
  Python calls to the tenant need a custom User-Agent (Cloudflare 403, "1010").
- SaaS Connectivity: connector `saas-connectivity-demo`, source `796ddbe4f7844c01a6d43f0cb39b85d4` (it created about 50 identities). Its CLI uses its own config folder.
- Demo campaign `a1ea0ee9-bc80-43de-8425-607c87c63eba` ("UCSF HackDay demo - …"; it replaced the unprefixed one, because active campaigns can't be renamed) is ACTIVE: Douglas.Flores has 1 certification (0/29 decisions, due 2026-10-19). Recreate it with
  `scripts/create_demo_campaign.py` (skips creation if it exists; sends no emails). SDK quirks: `create_campaign_v1` returns None; `start_campaign_v1` needs
  `ActivateCampaignOptions`; `to_dict()` drops read-only fields, so use `model_dump(by_alias=True)`.
- `notify_manager` → workflow `5e7f8d19-8cfd-4ad1-8bf7-c48dca84b830` ("UCSF Flagged Report to Manager"; enabled; EXTERNAL trigger,
  so it only runs when called). Its OAuth client is in `.env` as `SAIL_FLAGGED_WORKFLOW_*` and is used via `client.call_sailpoint_as()`;
  the PAT gets a 401 on that endpoint. Gotchas: the payload arrives under `$.trigger.input`; the client can only be generated while the workflow is
  disabled; a PUT that drops the `clientId`/`url` trigger attributes revokes the client (`identity-workflows/scripts/isc.py update` now keeps them).
  `get_workflow_execution_v1` fails to deserialize, so read `_without_preload_content` instead.
- Demo tenant: about 308 identities, 52 managers, no roles. Good demo managers: Douglas.Flores (4 reports, privileged
  and unique access), Neville.Kaufman (Sales; one rep has `Source Code`), Martena.Heath (19 reports; April.Rios never onboarded).
- **Team Access Radar** (the UI plugin, `ui-plugins/manager-lookup-shcotta/`, alias unchanged) is the in-product version of the review.
  Its rules (`src/app/team-access/team-flags.ts`) port `_team.py`. **Contract:** `shared/team-flag-cases.json` (generated by
  `shared/make_flag_cases.py` from Python, which is the reference) is run by `tests/test_flag_parity.py` AND the plugin's `team-flags.spec.ts`.
  If you change a flag rule, change Python, regenerate the cases, then port to TypeScript until both pass. Reason text must match exactly.
  The plugin calls `POST /v3/search?limit=250` and `GET /v3/certifications` as the signed-in user. Manifest changes: `../sail.sh ui-plugins push-manifest`.
  It is **uploaded** (named "UCSF Team Access Radar"); re-upload after changes with `npm run build && ../sail.sh ui-plugins upload`.
  Its **Email manager** button calls `POST /v3/workflows/7326ad5b-…/test` (the DISABLED "UCSF Flagged Report to Manager (Radar)" copy, which reads `$.trigger.*`),
  because a browser plugin can't hold the external trigger's secret. That only works for users allowed to test workflows (hack.day is ORG_ADMIN).
- **Don't install node_modules for the sandbox in the shared plugin or connector folders**; they belong to the Mac. Test and build in a scratch copy
  (rsync without node_modules; the plugin spec imports `../../../../../shared/team-flag-cases.json`, so mirror `shared/` next to `ui-plugins/`).

## Sandbox gotchas
- Egress firewall: a new host returns 403 "Approval required for <host>". The user approves it on the host with
  `sbx policy approval ls` / `sbx policy approval respond <id> --option allow`. Don't work around it.
- `git clone` from GitHub fails with a 401 (bad proxy creds). Use `https://codeload.github.com/<org>/<repo>/tar.gz/refs/heads/<branch>`.
- WebFetch is blocked for developer.sailpoint.com; use `curl` and strip the HTML.
- All egress goes through `HTTPS_PROXY` (gateway.docker.internal:3128). The SailPoint **Python SDK ignores it**;
  `sailpoint_mcp/client.py:proxy_for()` passes it through. Any other tool that does its own HTTP needs the same treatment.
- **Don't edit files with `sed -i` in this workspace.** On this mount it leaves files owner-only (0600) and drops the execute bit, so
  the user's Mac-side VS Code can't read them (the .vscode files became unreadable from the Mac). Use the Edit tool or Python `open(...,'w')`.
  Check with `find . -perm 600 -not -name .env -not -name config.json` (only `.env` files and the connector's `config.json` should match).
- Python's stdlib `venv` is broken; use `uv venv` and `uv pip install`.
- Reach in-sandbox servers via `localhost`, not 172.17.0.9 (that goes through the proxy). Dev servers bind 0.0.0.0, and the
  user publishes their ports with `sbx ports $(hostname) --publish <p>:<p>`.

## MCP Server track quick reference
- Run tests: `cd python-mcp-server-template && .venv/bin/python -m pytest -q`
- Credential check: `.venv/bin/python scripts/check_auth.py "Adam Kennedy"`
- Tools: `search_identities` (template), `review_team_access`, `get_identity_access`, `get_manager_pending_reviews`, `notify_manager`
  (shared logic in `src/sailpoint_mcp/tools/_team.py`, pure and unit-tested in `tests/test_team.py`).
- Inspector: `npx @modelcontextprotocol/inspector@latest --config mcp-inspector.json --server sailpoint`
