# Runbook: run, demo and clean up

Everything here runs from **VS Code on your Mac**, opened at `sailpoint_hackathon/`. The same folder is
mounted into the Claude Code sandbox, so both sides see the same files. Each side keeps its own
Python environment (`.venv-mac` on the Mac, `.venv` in the sandbox), so neither breaks the other.

## 1. One-time setup (Mac)
```bash
brew install uv node        # uv runs the Python server; node runs the Inspector and the UI plugin
```
Open the `sailpoint_hackathon` folder itself in VS Code (File → Open Folder) and install the recommended extensions when prompted.
The tenant credentials are already in `python-mcp-server-template/.env`, which is gitignored and never committed.

## 2. Run anything from the ▶ list
Open **Run and Debug** (⇧⌘D), pick an entry from the dropdown, and press **▶**. Python entries run under the debugger, so breakpoints in `src/` stop.

| Group | Entry | What you should see |
|---|---|---|
| **Setup** (run 1 once, first) | **1. Setup: install / update environment** | `Environment ready.` (creates `.venv-mac`) |
| | **2. Test: unit tests** | `45 passed` (no tenant needed) |
| | **3. Test: tenant connection** | three `OK` lines and Adam Kennedy's record |
| **Demo** | **Demo 1: review Douglas.Flores's team** | flags, with Brandon.Mason **high** first |
| | **Demo 2: Brandon.Mason's privileged access** | the two privileged AD entitlements |
| | **Demo 3: Douglas.Flores's pending reviews** | 1 open certification, 0/29 decisions |
| | **Demo 4: email Douglas about Brandon** ⚠️ sends an email | `"notified": true`; the email arrives at shane.cotta+hackday@gmail.com |
| | **Demo setup: create demo campaign** | `… is ACTIVE` (creates it only if missing) |
| **Tools** | **Tool: call any tool…** | pick a tool, type its JSON arguments |
| | **Tool: MCP Inspector (browser)** | open the printed `http://127.0.0.1:6274?…` link → **Connect** → **Tools** |
| | **Tool: attach to MCP server (sailpoint-debug)** | debug the live server while Chat uses it (see §3) |
| | **Team Access Radar (UI plugin): dev server** | for trying local changes: serves https://localhost:4200; open the plugin URL in §3a with `?spPluginDev=manager-lookup-shcotta` |
| **Other tracks** | **Team Access Radar (UI plugin): unit tests** | `56 passed` (includes the 6 shared parity cases) |
| | **Identity Workflows: validate workflow files** | `OK (0 errors, 0 warnings)` for all 4 workflows (offline) |
| | **Identity Workflows: test onboarding email** ⚠️ sends an email | test run completes; the onboarding email arrives at shane.cotta+hackday@gmail.com |
| | **SaaS connector: unit tests** | installs on first run, then the jest results |

## 3. Chat with it in VS Code (native MCP)
`.vscode/mcp.json` registers two servers, **`sailpoint`** and **`sailpoint-debug`**.
1. ⇧⌘P → **MCP: List Servers** → `sailpoint` → **Start**.
2. Open Chat in **Agent** mode and ask the demo questions in §5.
3. To debug what Chat does: start **`sailpoint-debug`** instead, then press ▶ on **Tool: attach to MCP server (sailpoint-debug)**. Breakpoints in `src/sailpoint_mcp/tools/` hit on every tool call.

> The Inspector only listens on localhost on your Mac, so there are no ports to publish and no safety override.
> Only if you ever need it *inside the sandbox*: run it with `DANGEROUSLY_BIND_ALL_INTERFACES=true HOST=0.0.0.0` and publish with
> `sbx ports $(hostname) --publish 127.0.0.1:6274:6274 --publish 127.0.0.1:6277:6277`.

## 3a. See it in the SailPoint UI
Log in at https://devrel-ga-25044.identitynow-demo.com as `hack.day`. Everything below was created by or for that account.
The MCP tools themselves run in an AI client, not in ISC. The UI shows what they read and what they create.
Menu names can differ slightly between ISC releases.

| What | Where in ISC | What you'll see |
|---|---|---|
| **The finding behind Demo 1–2** | Search (top bar) → `Brandon.Mason` → his identity → **Access** tab | `AccountingGeneral` and `AccountsPayable` (privileged) and `ENG_Prod`, the access the tool flagged |
| **Demo campaign (Demo 3)** | Admin → **Certifications** → Campaigns → *UCSF HackDay demo - team access review (Douglas.Flores)* | Active campaign, 1 certification for Douglas.Flores, 4 identities, 29 decisions, due 2026-10-19 |
| **Manager email workflow (Demo 4)** | Admin → **Workflows** → *UCSF Flagged Report to Manager* → **Execution History** | Every `notify_manager` run, with each step's input and output (including the rendered email) |
| **Onboarding workflows** | Admin → **Workflows** → *UCSF Identity Onboarding* (and *manager check*) | Open in the Builder to see the steps. **Test** (with a payload such as `data/test-payload.example.json`) re-runs it and sends the email. |
| **SaaS connector + source** | Admin → **Connections** → **Sources** → *UCSF SaaS Connectivity Demo (Hack Day)* | Accounts (50), Entitlements (8; `admin` marked privileged), aggregation history, Test Connection |
| **UCSF Team Access Radar (UI plugin)** | Open https://devrel-ga-25044.identitynow-demo.com/ui/plugin/0ac31b98-85df-4d2e-a6dd-7676f148a0ac (uploaded, so no dev server is needed). To try local code changes instead, run ▶ **Team Access Radar (UI plugin): dev server** and add `?spPluginDev=manager-lookup-shcotta` to that URL. | The team review *inside* ISC. Pick **Douglas.Flores**: 1 high and 5 medium flags (Brandon.Mason first), the team table with flag tags, shared access, and his open certification. Each flag has an **Email manager** button (⚠️ sends an email to the demo inbox). |

## 4. Claude Code
`.mcp.json` (in the workspace root and in `python-mcp-server-template/`) registers the same launcher. Start
`claude` and approve the `sailpoint` server when asked. `/mcp` should show it connected. This works both on the Mac and in the sandbox.

## 5. Live demo script (about 5 minutes)

### Before you present (5 minutes)
1. ▶ **3. Test: tenant connection**: three `OK` lines.
2. ▶ **Demo setup: create demo campaign**: says `… is ACTIVE`.
3. Start the server: ⇧⌘P → **MCP: List Servers** → `sailpoint` → **Start** (or start `claude` in the `sailpoint_hackathon` folder).
4. Open, in tabs: the chat panel (Agent mode), the demo inbox (shane.cotta+hackday@gmail.com), and ISC signed in as `hack.day` with the
   UCSF Team Access Radar plugin open.
5. Backup if the chat misbehaves: the ▶ **Demo 1–4** entries run the same tool calls directly and print the results.

| # | Ask | What it shows |
|---|---|---|
| 1 | *"Review Douglas.Flores's team access. What should he look at first?"* | `review_team_access` flags **Brandon.Mason** as high severity: privileged `AccountingGeneral` that nobody else on the team has, plus `ENG_Prod` on an Accounts Payable analyst. |
| 2 | *"What exactly is privileged about Brandon's access?"* | `get_identity_access(kind=privileged)` returns the two privileged AD entitlements. |
| 3 | *"Does Douglas have any reviews open where he can fix this?"* | `get_manager_pending_reviews` returns the open certification `Identity Access Review for Douglas.Flores`, 0/29 decisions, due 2026-10-19. |
| 4 | *"Now check Neville.Kaufman's sales team."* | A sales rep (Cooper.Stevenson) holds `Source Code`. |
| 5 | *"And Martena.Heath's call center?"* | April.Rios lacks all 8 baseline items, so she was never fully onboarded. |
| 6 | *"Let Douglas know about Brandon."* | `notify_manager` runs the SailPoint workflow and reports `notified: true` once the email is sent. Show the email arriving in shane.cotta+hackday@gmail.com: *"Your report Brandon.Mason … was flagged in a team access review."* |

| 7 | Switch to ISC and open **UCSF Team Access Radar**, then pick Douglas.Flores | The same flags, in the product, with the open certification next to them. The chat answer and the page come from the same rules. Press **Email manager** on Brandon's flag to show the in-product action. |

Step 3 needs the demo campaign. Press ▶ on **Demo setup: create demo campaign**. It does nothing if the campaign already exists, and it sends no emails.

## 6. What we created in the shared tenant (for clean-up)
| Object | ID / name | Created by | Remove with |
|---|---|---|---|
| Certification campaign | `a1ea0ee9-bc80-43de-8425-607c87c63eba`, "UCSF HackDay demo - team access review (Douglas.Flores)" | MCP track | Admin → Certifications → Campaigns → delete |
| UI plugin instance (private, uploaded), "UCSF Team Access Radar" | `0ac31b98-85df-4d2e-a6dd-7676f148a0ac` | UI Plugins | `python-mcp-server-template/ui-plugins/sail.sh ui-plugins delete …` |
| Workflows (disabled) | `499d37f2-…` "UCSF Identity Onboarding", `4f178d1b-…` "(manager check)" | Identity Workflows | Admin → Workflows → delete |
| Workflow (disabled; started by the plugin's Email manager button) | `7326ad5b-0113-49d8-94e0-81f821712a50` "UCSF Flagged Report to Manager (Radar)" | Team Access Radar | Admin → Workflows → delete |
| Workflow (enabled, external trigger only) + its OAuth client | `5e7f8d19-8cfd-4ad1-8bf7-c48dca84b830` "UCSF Flagged Report to Manager" | MCP track (`notify_manager`) | Admin → Workflows → delete (this also removes its trigger client) |
| Source + connector | source `796ddbe4f7844c01a6d43f0cb39b85d4` "UCSF SaaS Connectivity Demo (Hack Day)", connector `saas-connectivity-demo` (display name "UCSF SaaS Connectivity Demo") | SaaS Connectivity | delete source, then `sail conn delete -c saas-connectivity-demo` |
| Identities from aggregation | about 50, created by the SaaS demo source | SaaS Connectivity | removed with the source |

### Naming in the shared tenant
Everything we create in the tenant starts with **UCSF** (workflows, campaign, source, connector, plugin) so other teams can tell it apart.
Two IDs can't be renamed and keep their original values: the plugin alias `manager-lookup-shcotta` and the connector alias `saas-connectivity-demo`.

**Put the Radar in the ISC nav bar** (one-time, UI only): Admin → Global → System Settings → **Customize Navbar** → add a custom item
labelled **UCSF Team Access Radar** that points to the plugin → Save.

## 7. The other tracks
| Track | Start here | Status |
|---|---|---|
| UI Plugins → UCSF Team Access Radar | `python-mcp-server-template/ui-plugins/README.md` | 56 tests, live API calls verified, **uploaded** to the tenant (no dev server needed), with an Email manager button |
| Identity Workflows | `python-mcp-server-template/identity-workflows/README.md` | Workflow created and test-run green; delivery to shane.cotta+hackday@gmail.com confirmed; not enabled |
| SaaS Connectivity | `python-mcp-server-template/saas-connectivity/README.md` | Done: connector deployed, source aggregated (50 accounts, 8 entitlements). Demo key expires 2026-10-12 |

`node_modules` is not in git and is platform-specific. Run `npx -y npm@11 install` (UI plugin) or `npm install` (connector) on the Mac once before running those folders there.

## 8. Troubleshooting
| Symptom | Fix |
|---|---|
| ▶ list is empty or missing entries | VS Code must have `sailpoint_hackathon/` itself open (File → Open Folder), not a subfolder. After files change, run ⇧⌘P → **Developer: Reload Window**. |
| A Python entry says the interpreter `.venv-mac/bin/python` doesn't exist | Run **1. Setup** first. |
| `uv not found` when starting the server | `brew install uv`. The launcher also checks `/opt/homebrew/bin` and `~/.local/bin`. |
| 403 `Approval required for <host>` (sandbox only) | Run `sbx policy approval ls` and `sbx policy approval respond <id> --option allow` on the Mac |
| Python call to the tenant gets 403 `error code: 1010` | Cloudflare blocks the default Python User-Agent. Send a custom one (the SDK's is fine). |
| DNS errors from the SDK behind a proxy | `client.proxy_for()` forwards `HTTPS_PROXY`. Make sure the variable is set. |
| `notify_manager` returns 401 | The workflow's trigger client was revoked; this happens if the workflow is saved without its `clientId`/`url` trigger attributes. Disable the workflow, `POST /workflows/{id}/external/oauth-clients`, put the new `id`/`secret` in `.env` as `SAIL_FLAGGED_WORKFLOW_CLIENT_ID`/`_SECRET`, then re-enable it. |
| `notify_manager` says the workflow failed | Admin → Workflows → *Flagged Report to Manager* → Execution History shows which step failed. |
| Pending reviews come back empty | Press ▶ on **Demo setup: create demo campaign** and wait about a minute for it to activate. |

## 9. Repository layout
The whole `sailpoint_hackathon` folder is one git repository (`main`, remote https://github.com/Shane-Cotta/sailpoint_hackathon.git):
these docs and `.vscode/` at the top, and the code in `python-mcp-server-template/`. There the MCP server is at the root, and
`ui-plugins/`, `identity-workflows/` and `saas-connectivity/` each hold one track. The per-track worktrees used during
the parallel build have been removed. Nothing has been pushed anywhere yet.
