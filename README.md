# SailPoint Hack Day: our projects

**Theme: Manager Team Access Review.** A manager should be able to ask *"is anything wrong with my team's
access?"* and get a straight answer: who reports to them, what they can get into, what looks risky,
and what reviews are waiting on them.

Only the **main hack** is judged. We're entering **MCP Server**. The mini hacks are short guided tracks we
used to learn the platform and, where it made sense, to extend the same theme.

| Option | What it is | Status | Read more |
|---|---|---|---|
| **MCP Server** (main hack, judged) | Talk to SailPoint in plain language. Four new AI tools review a manager's team, drill into one person's access, list pending reviews, and email the manager through a SailPoint workflow. | ✅ Working against the live tenant, including a demo certification campaign and workflow emails to managers. 45 tests. | [python-mcp-server-template/README.md](python-mcp-server-template/README.md) |
| **UI Plugins → Team Access Radar** (mini hack 03, extended) | The team access review *inside* Identity Security Cloud: pick a manager to see flagged people with reasons, the team's shared access, and open certifications. Same rules as the MCP server, checked by shared tests. | ✅ 56 tests; live API calls verified; **uploaded** to the tenant as *UCSF Team Access Radar*, with an **Email manager** button on every flag. | [python-mcp-server-template/ui-plugins/README.md](python-mcp-server-template/ui-plugins/README.md) |
| **Identity Workflows** (mini hack 01) | A workflow that emails an onboarding notice when a new identity is created. | ✅ Created in the tenant and test-run green. Delivery confirmed. Its "flagged report → manager" workflow is live and called by the MCP server's `notify_manager`. | [python-mcp-server-template/identity-workflows/README.md](python-mcp-server-template/identity-workflows/README.md) |
| **SaaS Connectivity** (mini hack 02) | A cloud-hosted connector that brings a new system's accounts and entitlements into SailPoint. | ✅ Deployed; source aggregated (50 accounts, 8 entitlements). | [python-mcp-server-template/saas-connectivity/README.md](python-mcp-server-template/saas-connectivity/README.md) |

## How the main hack is judged
Use case 25% · Execution 25% · Creativity 20% · "Coolness" 20% · SailPoint API usage 10%. It must use at least one SailPoint API and be shown in a live demo.

## Try it in VS Code (2 minutes)
1. On the Mac, once: `brew install uv node`. Then open this `sailpoint_hackathon` folder in VS Code.
2. **Run and Debug (⇧⌘D)** → pick **1. Setup: install / update environment** → ▶
3. Then pick and ▶ any of: **2. Test: unit tests**, **3. Test: tenant connection**, **Demo 1–4**, the **Tool** entries, or the **other tracks**.

Or chat with it: ⇧⌘P → **MCP: List Servers** → `sailpoint` → **Start**, then in Agent mode ask
*"Review Douglas.Flores's team access and tell me what to look at first."* Every entry and what it shows is in [RUNBOOK.md §2](RUNBOOK.md#2-run-anything-from-the--list).

## More
- **[RUNBOOK.md](RUNBOOK.md)**: run it in VS Code, the demo script, and what to clean up in the tenant.
- **[AGENT-WORKFLOW.md](AGENT-WORKFLOW.md)**: how one orchestrating Claude session and three subagents built all of this in parallel (with diagrams).

This whole folder is one git repository (https://github.com/Shane-Cotta/sailpoint_hackathon). The code is in `python-mcp-server-template/`: the MCP server at its root, and each other track in its own folder.
