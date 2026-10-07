# Bulk Access Request for SailPoint Identity Security Cloud

Request access for **many people at once**, approved by **one person you choose**, and tracked by a
**ServiceNow INC number**.

> *"These 12 new contractors all need the same three access profiles for INC0012345. Have Dana approve it once."*

1. **Pick the people:** search for them, or paste a list (the plugin accepts pasted usernames or emails).
2. **Pick the access:** one or more items from the Request Center catalog.
3. **Pick one approver** for the whole request. It can't be you.
4. **Enter the INC number** (checked for the right format) and a justification.
5. **Submit.** The approver gets **one** approval task. If they approve, everyone gets every item as a normal SailPoint
   access request, and each request's comment reads `INC… | Bulk access request by … | Approved by … | <justification>`.
   If they deny, nothing is requested. Either way, the requester gets an email.

## Two ways to deploy it (each installs on its own)

| | **A. Launcher** (native) | **B. UI plugin** |
|---|---|---|
| Where users find it | **Launchpad**, as a native SailPoint form | A page inside ISC, reachable from a nav-bar link |
| Who can use it | **Any user** you give the *Launcher Access* profile to (they can request it in the Request Center) | **ORG_ADMIN-level users only** (see the plugin README) |
| Choosing people | Form picker, up to 30 people (SailPoint's form limit) | Search or paste a list, no 30 limit, warns about access people already have |
| Status tracking | Approval email, plus the requests in Request Center → *Track My Requests* | **My bulk requests** tab, grouped by INC |
| Install | `launcher/install.py` | `plugin/install.py` + `sail ui-plugins upload` |
| Docs | [INSTALL.md](INSTALL.md) §A, [USAGE.md](USAGE.md) | [plugin/README.md](plugin/README.md) |

**Not sure which?** Start with **A**: it works for everyone and needs nothing but this folder. Add **B** if your
admins or service desk want the richer screen. Both can run side by side in one tenant.

## What gets created in the tenant
Everything is named with your **prefix** (for example `ACME`), so it is easy to find and to remove:

- **A:** *"ACME Bulk Access Request Form"*, the *"ACME Bulk Access Request"* workflow and Launcher, and the
  *"ACME Bulk Access Request - Launcher Access"* access profile.
- **B:** the *"ACME Bulk Access Request (Plugin)"* workflow (kept disabled, by design) and the *ACME Bulk Access Request* UI plugin.

## Safe by default
- **New installs start in `dry-run` mode.** The whole flow runs (form, approval, emails), but nothing is requested
  until you switch `"mode": "live"`.
- **The catalog can be limited** to item names starting with a given text (`catalog.nameStartsWith`).
- **All email can be redirected** to a test inbox (`notifications.overrideRecipients`).
- **The approver is never the requester:** SailPoint would quietly reassign that approval to another admin, so it's blocked up front.

## Screenshots
Real SailPoint screens (`docs/screenshots/`) from a test installation that used the prefix `UCSF`; yours show your own prefix:

| Launcher (A) | |
|---|---|
| ![Request the tool in the Request Center](docs/screenshots/launcher-0-request-center-access.png) | ![Launchpad](docs/screenshots/launcher-1-launchpad.png) |
| *Users request "Launcher Access" in the Request Center* | *…then launch it from the Launchpad* |
| ![The form](docs/screenshots/launcher-4-form-filled.png) | ![INC validation](docs/screenshots/launcher-3-inc-validation.png) |
| *People, items, one approver, INC, justification* | *A bad INC can't be submitted* |

| UI plugin (B), running inside SailPoint | |
|---|---|
| ![New request](docs/screenshots/plugin-in-isc-1-new-request.png) | ![My bulk requests](docs/screenshots/plugin-in-isc-2-my-bulk-requests.png) |
| *Four steps: people, access, approver and INC, review* | *Everything you've submitted, by INC* |

More plugin screens (made with sample data, one per step) are in [plugin/README.md](plugin/README.md).

## Folder layout
```
bulk-access-request/
├── README.md  INSTALL.md  USAGE.md        ← start here
├── config/bulk-access.example.json        ← copy to config/<tenant>.json (your copies stay out of git)
├── core/        shared Python package: config, API client, rules, definitions (+ tests)
├── launcher/    deployment A: install.py · status.py · uninstall.py · e2e.py
├── plugin/      deployment B: the Angular UI plugin + its install/status/uninstall
└── docs/screenshots/
```

## Tested
Both deployments were installed in a live Identity Security Cloud tenant and verified end to end with test identities and a
test access profile:
- **Launcher:** dry-run approve and deny; live approve (one real request per person, carrying the INC, requester and
  approver in its comment); live deny; self-approval stopped before any approval exists.
- **UI plugin:** dry-run approve, live approve, live deny, invalid INC.
- **Unit tests:** core 27, plugin installer 10, plugin UI 45 (`pytest`, `ng test`), none of them needing a tenant.
