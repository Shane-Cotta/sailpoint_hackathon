# Bulk Access Request — developer guide

Bulk access requests for SailPoint Identity Security Cloud (ISC): many people × many Request Center items, approved by
**one** chosen approver, tracked by a **ServiceNow INC number**. Two independently installable deployments share one core.
Human docs: `README.md` (overview), `INSTALL.md` (any tenant), `USAGE.md` (requesters, approvers, admins), `plugin/README.md`.

## Layout
| Path | What |
|---|---|
| `core/bulkaccess/` | Shared Python (standard library only): `config.py` (tenant config), `tenant.py` (PAT client), `rules.py` (validation), `definitions.py` (pure JSON builders for the form, workflow and launcher) |
| `launcher/` | Deployment A: `install.py`, `status.py`, `uninstall.py`, `e2e.py` |
| `plugin/` | Deployment B: Angular + PrimeNG UI plugin, plus `install.py` / `status.py` / `uninstall.py` / `pluginlib.py` |
| `config/` | `bulk-access.example.json` (committed). Per-tenant `config/<tenant>.json` files are **gitignored**. |
| `docs/screenshots/` | Images used by the docs |

## Conventions
- **No tenant-specific anything in code.** Names come from the config `prefix`, IDs are looked up by name at install time.
  Example values use the placeholder prefix `ACME`.
- **New installs default to `mode: dry-run`**; `live` actually requests access. Test with test identities and a harmless
  test access profile, and set `notifications.overrideRecipients` in shared or test tenants.
- **Never commit credentials.** The PAT comes from `SAIL_BASE_URL` / `SAIL_CLIENT_ID` / `SAIL_CLIENT_SECRET` (env or the config's `envFile`).
- Python changes: keep `core` dependency-free and pure where possible; update `core/tests/test_core.py`.
- The plugin's `src/app/bulk/rules.ts` mirrors `core/bulkaccess/rules.py`; change both together (their specs mirror each other).
- Plugin: `npx -y npm@11 install` (npm 11.12+), `npx ng test --watch=false`, `npm run build`. SailPoint CLI `sail` ≥ 2.7.0 for upload.
  **Never run `sail` with `--debug`** (it persists and prints tokens). `sail ui-plugins push-manifest` replaces the whole manifest,
  so the installer always passes `--private` unless `--public` is asked for.

## ISC behaviour this design depends on (all verified against a live tenant)
- **Forms:**
  - REGEX validation is `{"validationType":"REGEX","config":{"regex":…,"message":…}}`.
  - **Never** put a MAX_LENGTH rule on a TEXTAREA: the submission then never reaches the workflow.
  - A SELECT allows at most 30 selections.
  - STATIC select options may carry full `{id,type,name}` objects. INTERNAL selects ignore queries; SEARCH selects return names, not IDs.
  - The INTERNAL identity picker only matches complete usernames, and doesn't list uncorrelated identities.
  - Through the API, a form may need two PATCHes to go ASSIGNED → IN_PROGRESS → SUBMITTED.
- **Generic Approval:**
  - `approvalType SINGLE`, `singleApproverCategory IDENTITY`, `singleApproverIdentityId.$`. Branch on `$.<step>.status` (`APPROVED`).
  - A self-approval is silently reassigned to some admin, so it's blocked up front.
  - An ORG_ADMIN can approve or reject on someone's behalf (`/v2025/generic-approvals/{id}/approve|reject`). That's recorded as a manual reassignment: the original approver is the first `reassignmentHistory[].reassignedFrom`.
- **Requesting access from a workflow:**
  - `sp:create-approval-request` breaks on one-item lists (the engine unwraps single-element arrays); use `sp:access:manage`.
  - A request takes at most 10 recipients, and nested loops are rejected, so the workflow loops over people and each request carries all the items.
  - Steps inside a loop only see `$.loop.*`, so the loop gets `context.$: "$"` and reads `$.loop.context.…`.
- **Workflow definitions:** failure end steps need top-level `failureName` / `description`. Launcher-triggered workflows must filter
  `$[?(@.workflowId == '<own id>')]`.
- **Launchers:**
  - Visible and launchable only for holders of the auto-created `assignedLaunchers` entitlement (on the IdentityNow source). The installer wraps it in a requestable "Launcher Access" profile.
  - Disabling the workflow disables its Launcher a moment later.
- **Plugins:** a browser plugin can't hold a workflow's external-trigger secret, so the plugin uses the workflow **test** endpoint. That
  requires a disabled workflow and an ORG_ADMIN user.
- **APIs:**
  - `/v3/requestable-objects` needs `types=` repeated; a comma list containing ENTITLEMENT returns 400.
  - There's no v3 identities API; use `/v2025/identities`.
  - Some tenants sit behind Cloudflare, which rejects Python's default User-Agent; the client sends its own.
