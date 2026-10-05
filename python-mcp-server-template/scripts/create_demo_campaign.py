#!/usr/bin/env python3
"""Create (and activate) a small certification campaign for the Hack Day demo.

    python scripts/create_demo_campaign.py                  # Douglas.Flores's team
    python scripts/create_demo_campaign.py "Neville.Kaufman"

Gives `get_manager_pending_reviews` something real to show: a search campaign
covering exactly the manager's direct reports, with the manager as reviewer.
Email notifications are off so nobody gets mailed from the shared tenant.
Idempotent -- if a campaign with the same name exists, it is reported and left
alone.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sailpoint import CertificationCampaignsApi  # noqa: E402
from sailpoint.certification_campaigns.models.activate_campaign_options import (  # noqa: E402
    ActivateCampaignOptions,
)
from sailpoint.certification_campaigns.models.campaign2 import Campaign2  # noqa: E402
from sailpoint.certification_campaigns.models.campaign2_all_of_search_campaign_info import (  # noqa: E402
    Campaign2AllOfSearchCampaignInfo,
)
from sailpoint.certification_campaigns.models.campaign2_all_of_search_campaign_info_reviewer import (  # noqa: E402
    Campaign2AllOfSearchCampaignInfoReviewer,
)

from sailpoint_mcp.client import call_sailpoint, describe_api_error  # noqa: E402
from sailpoint_mcp.tools import _team  # noqa: E402

# "UCSF" marks our resources in the shared demo tenant.
NAME_PREFIX = "UCSF HackDay demo - team access review"

# Campaigns generate asynchronously (PENDING -> STAGED) and can only be
# activated once STAGED.
STAGE_TIMEOUT_SECONDS = 180


def find_campaign(name: str) -> dict | None:
    found = call_sailpoint(
        lambda c: CertificationCampaignsApi(c).get_active_campaigns_v1(
            filters=f'name eq "{name}"', limit=5
        )
    )
    for item in found or []:
        model = getattr(item, "actual_instance", None) or item
        # Read attributes directly: the SDK's to_dict() drops read-only fields
        # such as id and status.
        return {"id": model.id, "status": model.status}
    return None


def activate_when_staged(name: str) -> int:
    deadline = time.monotonic() + STAGE_TIMEOUT_SECONDS
    while True:
        campaign = find_campaign(name)
        status = (campaign or {}).get("status")
        if status in ("ACTIVE", "ACTIVATING", "COMPLETED", "COMPLETING"):
            print(f"OK  {name} is {status} id={campaign['id']}")
            return 0
        if status == "STAGED":
            # The endpoint rejects an empty body, so always send the options.
            call_sailpoint(
                lambda c: CertificationCampaignsApi(c).start_campaign_v1(
                    id=campaign["id"],
                    activate_campaign_options=ActivateCampaignOptions(time_zone="Z"),
                )
            )
            print(f"OK  activation requested for id={campaign['id']}")
            return 0
        if time.monotonic() > deadline:
            print(f"FAIL: campaign still {status} after {STAGE_TIMEOUT_SECONDS}s; re-run later")
            return 1
        time.sleep(5)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    manager_query = sys.argv[1] if len(sys.argv) > 1 else "Douglas.Flores"

    try:
        manager = _team.resolve_identity(manager_query)
    except _team.IdentityNotResolved as exc:
        print(f"FAIL: {exc.payload}")
        return 1
    manager_name = manager.get("displayName") or manager.get("name")
    name = f"{NAME_PREFIX} ({manager_name})"

    if find_campaign(name):
        print(f"OK  already exists: {name}")
        return activate_when_staged(name)

    reports = _team.fetch_direct_reports(manager["id"], limit=50)
    if not reports:
        print(f"FAIL: {manager_name} has no direct reports")
        return 1

    campaign = Campaign2(
        name=name,
        description=(
            f"Hack Day demo: {manager_name} reviews the access of their "
            f"{len(reports)} direct reports. Safe to delete."
        ),
        type="SEARCH",
        deadline=datetime.now(timezone.utc) + timedelta(days=14),
        email_notification_enabled=False,
        auto_revoke_allowed=False,
        recommendations_enabled=False,
        search_campaign_info=Campaign2AllOfSearchCampaignInfo(
            type="IDENTITY",
            description=f"Direct reports of {manager_name}",
            identity_ids=[r["id"] for r in reports],
            reviewer=Campaign2AllOfSearchCampaignInfoReviewer(
                type="IDENTITY", id=manager["id"], name=manager_name
            ),
        ),
    )

    try:
        # The SDK cannot deserialize this endpoint's response and returns None,
        # so look the campaign up by name afterwards instead of trusting it.
        call_sailpoint(
            lambda c: CertificationCampaignsApi(c).create_campaign_v1(campaign2=campaign)
        )
        print(f"OK  created: {name}")
        return activate_when_staged(name)
    except Exception as exc:
        print(f"FAIL: {describe_api_error(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
