# Hack Day Track 01: Identity Workflows

**The track** ([guide](https://developer.sailpoint.com/hack-day/identity-workflows)): turn an identity event into a message. You build an HR feed (a delimited-file source plus an identity profile), then finish a Workflow Studio workflow. It fires on `idn:identity-created`, waits 1 minute, looks up the new hire and their manager, and sends an onboarding email that includes the new hire's name, department and job title, plus the manager's name and email.

**What we built**
- `Shane Cotta Identity Onboarding` (id `499d37f2-bbab-433d-b285-524b559c0338`): the track's template plus our **Send Email** step. We created it in the tenant through the Workflows API (it is disabled) and ran it with Test Workflow. The run went green, and the email it rendered had all 6 required values ([evidence](evidence/test-run-juan-hamilton.txt)).
- `Shane Cotta Identity Onboarding (manager check)` (id `4f178d1b-…`): the "survive a missing manager" stretch goal. A choice step sends a "no manager on record, routing to HR" email instead of failing. We tested both branches and both went green.
- Two more definitions that we validated offline but did **not** create in the tenant: `to-manager` (a stretch goal) and `flagged-report-to-manager` (the main-hack tie-in, see below).
- `scripts/`: `build_workflow.py` builds the JSON from the guide's template, `validate_workflow.py` is an offline linter, and `isc.py` is a stdlib-only API client (create, update, test, history).

**Reproduce**
```bash
cd identity-workflows            # needs .env with SAIL_BASE_URL / SAIL_CLIENT_ID / SAIL_CLIENT_SECRET
python3 scripts/build_workflow.py --recipient you@yourmail.com
python3 scripts/validate_workflow.py workflow/*.json
python3 scripts/isc.py update workflow/identity-onboarding.workflow.json   # pushes your recipient to the existing workflow
python3 scripts/isc.py find-identity Juan.Hamilton                          # pick a test identity that has a manager
python3 scripts/isc.py test workflow/identity-onboarding.workflow.json <identity-id> <name>
```
No CLI? Use the UI instead: Admin → Workflows → *Shane Cotta Identity Onboarding* → Edit in Builder → click **Send Onboarding Email** → replace the recipient → Save → Test Workflow, and paste `data/test-payload.example.json` with a real identity id.

**Status: partly done. The workflow is built and tested; the end-to-end joiner run is blocked.**
- **Recipient:** `shane.cotta+hackday@gmail.com` (set 2026-10-05, pushed to both tenant workflows; delivery confirmed in the inbox with all fields rendered).
- **This tenant was not set up for the mini hack.** It has no *Workflows Mini Hack Template*, no reference HR source, and no Margaret Hamilton or Jean Bartik. We followed the guide's fallback (build from `workflows-hack-day-template.json`) and tested against existing identities (Juan.Hamilton → manager Patrick.Jenkins).
- **Not done (needs the UI, or your OK to change the shared tenant):** Part 1 (your own delimited-file source, the schema, manager correlation, aggregating `guide-files/hr-feed.csv`, and the identity profile), step 4 (Enable) and step 5 (aggregate `data/hr-feed-with-new-hire.csv` so that a real `idn:identity-created` fires). The click-paths are in [NOTES.md](NOTES.md#ui-steps-left-for-you). Enabling the workflow subscribes it to *every* identity creation in this shared tenant, so add a trigger filter first or keep the window short.

**Main-hack tie-in (manager team access review)**
Our MCP tools (`review_team_access`, `get_identity_access`, `get_manager_pending_reviews`) find problems. A workflow is a good way to *act* on them without code:
- ✅ **Live:** `workflow/flagged-report-to-manager.workflow.json` is deployed as *Shane Cotta Flagged Report to Manager* (`5e7f8d19-…`, enabled, external trigger only) and called by the MCP server's **`notify_manager`** tool. The first live run delivered the email for Brandon.Mason → Douglas.Flores to the demo inbox. It uses an **EXTERNAL trigger**, so the MCP server POSTs `{identityId, flag, detail}` to it when a report is flagged (a leaver who still has access, access that is privileged or unusual compared with peers, or an overdue certification). The workflow looks up the report and the manager and emails the manager, using the same Get Identity → Get Manager → Send Email pattern as this track.
- An event version could react on its own: `idn:identity-attributes-changed` filtered to lifecycle → inactive would mean "a leaver just appeared, tell their manager to review." The guide's later stretch goals (Manage Access, a Create Form approval) would turn the alert into a one-click revoke.

**External-trigger gotchas** (found while wiring up `notify_manager`):
- The POSTed body arrives under **`$.trigger.input`**, so the workflow reads `$.trigger.input.identityId`, not `$.trigger.identityId`.
- The trigger's OAuth client can only be generated while the workflow is **disabled**, and the response calls the client id `id`.
- A PUT that omits the trigger's server-managed attributes (`clientId`, `url`) **silently revokes the client**. `scripts/isc.py update` now keeps them.
- The external-execute endpoint rejects PATs (401); it needs the workflow's own client.
