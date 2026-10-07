# Using Bulk Access Request

Guides for requesters, approvers and admins. Screenshots live in [docs/screenshots/](docs/screenshots/).

## Requesters, with the Launcher (any user)
1. **Get access to the tool, once.** In the **Request Center**, request **"<prefix> Bulk Access Request - Launcher
   Access"**. Your manager may need to approve it. After about a minute it shows up in your **Launchpad**.
2. **Launchpad → "<prefix> Bulk Access Request"**. A form opens:

   | Field | What to enter |
   |---|---|
   | **People who need the access** | Search and add up to 30 people |
   | **Access to request** | One or more items. *Everyone* above gets *every* item chosen here. |
   | **Approver** | The one person who decides. It can't be you. |
   | **ServiceNow incident (INC) number** | For example `INC0012345`. The form won't submit until the format is right. |
   | **Business justification** | Shown to the approver and stored on every request |
3. **Submit.** The Launchpad shows *"Sent to <approver> for approval."*
4. **You get an email** when it's decided. If approved, each person's request appears in
   **Request Center → Track My Requests** with your INC in the comment.

## Requesters, with the UI plugin (admins)
Open **<prefix> Bulk Access Request** from the nav bar, or the plugin link your admin gave you, and follow the four
steps: people → items → approver and INC → review. You can paste a list of usernames or emails. The
**My bulk requests** tab shows everything you've submitted, grouped by INC. Details are in [plugin/README.md](plugin/README.md).

## Approvers
- You get **one** approval task per bulk request, named **"Bulk access INC…"**, showing the requester and the
  justification. It arrives in your **SailPoint approvals** (and by email, if notifications are on).
- **Approve:** everyone on the request gets every item, as normal access requests.
- **Deny:** nothing is requested, and the requester is told.
- The task expires after the configured number of days (7 by default).

## Admins
- **Install, update, uninstall:** see [INSTALL.md](INSTALL.md). Check health with `python launcher/status.py --config …`.
- **When the catalog changes:** `python launcher/install.py --config … --sync-catalog`.
- **Who can use it:** whoever holds the *Launcher Access* profile. It's an ordinary access profile, so it shows up in
  certifications too.
- **Audit:**
  - Every request made by the tool has `INC… | Bulk access request by <requester> | Approved by <approver> | <justification>` as its comment.
  - The approval decisions are in the generic approvals history.
  - Each run is in **Admin → Workflows → "<prefix> Bulk Access Request" → Execution History**.
- **Test safely:**
  - Keep `"mode": "dry-run"` until you've run `launcher/e2e.py` on test identities.
  - In shared or test tenants, set `notifications.overrideRecipients` so emails don't reach real people.
