# Installing Bulk Access Request in any ISC tenant

This guide covers deployment **A (Launcher)** end to end, plus the setup both deployments share. Deployment
**B (UI plugin)** has its own guide in [plugin/README.md](plugin/README.md); it uses the same config file.

## 1. Prerequisites
| You need | Why |
|---|---|
| **Python 3.10+** (nothing to `pip install`) | The installers use only the standard library. |
| A **Personal Access Token** for an **ORG_ADMIN** user, scope `sp:scopes:all` | Creates the form, workflow, launcher and access profile. Everything created is owned by that user. |
| Workflows, **Forms** and **Launchers** available in the tenant | Standard in Identity Security Cloud. |
| Something in the **Request Center** catalog | The form offers requestable access profiles, roles or entitlements. |

Create the PAT under **Preferences → Personal Access Tokens → New Token** → *Other / No associated vendor
integration* → scope `sp:scopes:all`. Copy the secret straight away; it's shown only once.

## 2. Credentials
The installers read three environment variables. Put them in a `.env` file (and point `envFile` at it in your
config) or export them in your shell:
```bash
SAIL_BASE_URL=https://<tenant>.api.identitynow.com      # the *.api.* host
SAIL_CLIENT_ID=<PAT client id>
SAIL_CLIENT_SECRET=<PAT secret>
```
Keep that file private (`chmod 600 .env`) and out of git. `config/*.json` is already gitignored, apart from the example.

## 3. Configure
```bash
cp config/bulk-access.example.json config/<tenant>.json
```
| Setting | What it does | Default |
|---|---|---|
| `envFile` | Path to the `.env` above | `.env` |
| `prefix` | Starts the name of every object created, e.g. `ACME` → "ACME Bulk Access Request" | `ACME` |
| `mode` | `dry-run`: approvals run but nothing is requested. `live`: approved requests are submitted | `dry-run` |
| `inc.pattern` / `inc.example` / `inc.message` | INC format (a regex), the example shown in the field, and the error message | `^INC\d{7}$` |
| `catalog.types` | Which Request Center item types to offer | all three |
| `catalog.nameStartsWith` | Only offer items whose names start with this text (`null` = all) | `null` |
| `catalog.maxItems` | Most items per request (SailPoint's limit is 25) | 25 |
| `people.max` | Most people per request (the Launcher form is capped at 30 by SailPoint) | 50 |
| `approval.timeoutDays` / `actionAtTimeout` / `priority` | The approval task's deadline, what happens when it passes (`EXPIRED` or `APPROVED`), and its priority | 7 / EXPIRED / MEDIUM |
| `notifications.overrideRecipients` | Send **all** emails to these addresses instead of the real requester (use this in test tenants) | `[]` |
| `notifications.ccApprover` | Copy the approver on the outcome email | `true` |
| `launcher.accessApproval` | Who approves requests for the *Launcher Access* profile: `MANAGER` or `NONE` | `MANAGER` |
| `owner` | Owner identity ID for created objects (`null` = the PAT user) | `null` |
| `plugin.alias` / `plugin.displayName` | Deployment B only | `acme-bulk-access` |

## 4. Install deployment A (Launcher)
```bash
python launcher/install.py --config config/<tenant>.json --dry-run     # prints every JSON body; changes nothing
python launcher/install.py --config config/<tenant>.json --grant me    # installs, and gives *you* Launcher access
python launcher/status.py  --config config/<tenant>.json               # everything should say [ok]
```
The installer is **idempotent**: run it again at any time. It finds its objects by name and updates them. It creates:
1. **Form** "<prefix> Bulk Access Request Form". Its item list is the Request Center catalog filtered by your config.
2. **Workflow** "<prefix> Bulk Access Request". It's enabled, and it only reacts to *its own* Launcher.
3. **Launcher** "<prefix> Bulk Access Request". Users see it in their **Launchpad**.
4. **Access profile** "<prefix> Bulk Access Request - Launcher Access". SailPoint only shows a Launcher to people
   who hold its `assignedLaunchers` entitlement, so this profile controls who can use the tool. People request it
   in the **Request Center**, approved by their manager if `launcher.accessApproval` is `MANAGER`. Or grant it right away:
   `--grant <identityId>,<identityId>` (or `--grant me`).

**When the catalog changes**, refresh the form's choices:
`python launcher/install.py --config config/<tenant>.json --sync-catalog`.

## 5. Verify end to end, before going live
`launcher/e2e.py` drives the whole flow through the API, playing both the requester and the approver:
```bash
python launcher/e2e.py --config config/<tenant>.json \
    --people <testIdentityId>,<testIdentityId> --approver <otherTestIdentityId> --scenario approve
#   --scenario deny   → the approver says no, so nothing is requested
#   --scenario self   → the requester names themselves; the run stops before any approval exists
```
- **Who it runs as:** the PAT user, who needs Launcher access (`--grant me`).
- **What it does:** submits the form with a random INC, checks that **one** approval went to `--approver`,
  approves or rejects it on their behalf (ORG_ADMIN), and checks the result.
- **In `live` mode**, it also checks that every person got a request whose comment carries the INC.
- **Use test identities and a harmless test item.** In `live` mode, approved runs really request access.
- **The safe sequence:** dry-run approve → dry-run deny → (`"mode": "live"`, re-install) live approve on test
  identities → back to dry-run until you're ready.

## 6. Go live
Set `"mode": "live"` (and clear `overrideRecipients`) in your config, then run `install.py` again. `status.py` shows
`installed mode=live`.

## 7. Uninstall
```bash
python launcher/uninstall.py --config config/<tenant>.json          # lists what it would delete
python launcher/uninstall.py --config config/<tenant>.json --yes    # deletes the Launcher, access profile, workflow and form
```
- It only deletes objects whose names this config produces. All of them start with the prefix.
- Access already granted *through* bulk requests stays in place: it's ordinary access now, and it shows up in certifications as usual.

## How it works
```
Launchpad ─► Launcher ─► Workflow "<prefix> Bulk Access Request"
                           1. Interactive Form   people · items · approver · INC · justification
                           2. checks             approver ≠ requester · INC matches the pattern
                           3. Generic Approval   ONE task, assigned to the chosen approver
                           4. if APPROVED (live) Loop over people → Manage Access (all items for that person)
                           5. email              approved / denied (dry-run says nothing was requested)
```
Some of this design comes from limits we hit on a live tenant:
- **One request per person.** SailPoint caps a request at **10 recipients**, and **nested loops aren't allowed**.
  So the workflow loops over the people, and each request carries *all* the items. That has no size limit.
- **Catalog items are stored as full objects.** Each form choice holds the complete `{id, type, name}`, so the
  workflow never has to rebuild items from bare IDs. Re-run `--sync-catalog` when the catalog changes.
- **Inside a loop, steps only see `$.loop.*`.** So the workflow passes its whole state in as the loop context,
  which is how the INC and names reach every request's comment.
- **Self-approval is blocked up front.** SailPoint reassigns a self-approval to some other admin.
- **The trigger is scoped to its own Launcher.** "Interactive process launched" fires for every Launcher, so the
  workflow filters on its own ID.
- **The installer re-enables the Launcher.** Disabling a workflow, which happens during updates, switches its
  Launcher off a moment later; the installer checks and turns it back on.

## Troubleshooting
| Symptom | Fix |
|---|---|
| The Launcher isn't in someone's Launchpad | They need the *Launcher Access* profile. Request or grant it, wait about a minute, then refresh. |
| `HTTP 401 insufficient authorization` when launching | Same as above: the user doesn't hold the launcher's entitlement yet. |
| `HTTP 409 launcher is disabled` | Re-run `install.py`; it re-enables the Launcher. |
| The form offers nothing to request | Check `catalog.types` / `catalog.nameStartsWith`, then run `--sync-catalog`. |
| An approval went to someone unexpected | The requester chose themselves. That's now blocked; check the workflow is up to date (`status.py`). |
| HTTP 403 with "error code: 1010" from scripts | A proxy or Cloudflare is blocking the request. The client sends its own User-Agent; check `HTTPS_PROXY`. |
