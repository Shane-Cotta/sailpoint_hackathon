#!/usr/bin/env python3
"""Regenerate shared/team-flag-cases.json from the Python reference implementation.

    python shared/make_flag_cases.py

The team-review flag rules exist twice: in Python (`sailpoint_mcp.tools._team`,
used by the MCP server) and in TypeScript (`ui-plugins/.../team-flags.ts`, used
by the Team Access Radar plugin). Both test suites load the JSON this script
writes and must reproduce every expected flag exactly -- type, severity, items
and reason text -- so the chat answer and the in-product answer never disagree.

Change a rule in Python, re-run this, and the TypeScript tests show what to port.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sailpoint_mcp.tools import _team  # noqa: E402

OUT = Path(__file__).with_name("team-flag-cases.json")


def access(kind: str, name: str, source: str | None = None, privileged: bool = False) -> dict:
    item = {"id": f"{kind}-{source}-{name}", "type": kind, "name": name}
    if source:
        item["source"] = {"name": source}
    if privileged:
        item["privileged"] = True
    return item


def person(id_: str, name: str, items: list[dict], *, count: int | None = None,
           accounts: list[str] = ("Active Directory",), **extra) -> dict:
    doc = {
        "id": id_,
        "displayName": name,
        "access": items,
        "accounts": [{"id": f"{id_}-{s}", "name": name, "source": {"name": s}} for s in accounts],
        **extra,
    }
    if count is not None:
        doc["accessCount"] = count
    return doc


AD, PRISM = "Active Directory", "PRISM"
BASE = [
    access("ACCESS_PROFILE", "Employee Base Account - AD"),
    access("ENTITLEMENT", "All_Users", AD),
    access("ENTITLEMENT", "campusAccess", AD),
    access("ENTITLEMENT", "Internal_Employee", PRISM),
]
ROLE = access("ROLE", "Accounting Analyst")

CASES = [
    {
        "name": "accounting team: privileged access only one person has is high",
        "members": [
            person("brandon", "Brandon.Mason", BASE + [
                access("ENTITLEMENT", "AccountingGeneral", AD, privileged=True),
                access("ENTITLEMENT", "AccountsPayable", AD, privileged=True),
                access("ENTITLEMENT", "ENG_Prod", AD),
            ], count=7),
            person("nicole", "Nicole.Morales", BASE + [
                access("ENTITLEMENT", "AccountsPayable", AD, privileged=True),
                access("ENTITLEMENT", "DataArchive", AD),
            ], count=6),
            person("adam", "Adam.Kennedy", BASE + [access("ENTITLEMENT", "Create_Reports", PRISM)], count=5),
            person("bruce", "Bruce.Henry", BASE, count=4),
        ],
    },
    {
        "name": "leaver who still holds access is high, inactive with nothing is quiet",
        "members": [
            person("ann", "Ann", BASE, count=4, lifecycleState="active"),
            person("bob", "Bob", BASE[:2], count=2, lifecycleState="terminated"),
            person("cy", "Cy", [], count=0, accounts=[], inactive=True),
        ],
    },
    {
        "name": "no_roles only in a team that normally uses roles",
        "members": [
            person("p1", "P1", BASE + [ROLE], count=5),
            person("p2", "P2", BASE + [ROLE], count=5),
            person("p3", "P3", BASE, count=4),
        ],
    },
    {
        "name": "not fully onboarded, and an access outlier",
        "members": [
            *[person(f"p{i}", f"Rep{i}", BASE, count=4) for i in range(5)],
            person("april", "April.Rios", [], count=0, accounts=["HR"]),
            person("max", "Max.Access", BASE + [
                access("ENTITLEMENT", f"Extra{i}", AD) for i in range(6)
            ], count=10),
        ],
    },
    {
        "name": "two-person team: no peer comparison",
        "members": [
            person("a", "A", BASE + [access("ENTITLEMENT", "Source Code", AD)], count=5),
            person("b", "B", BASE, count=4),
        ],
    },
    {"name": "empty team", "members": []},
]


def main() -> None:
    cases = []
    for case in CASES:
        members = [_team.build_member(doc) for doc in case["members"]]
        cases.append({
            "name": case["name"],
            "documents": case["members"],
            "expected_flags": _team.team_flags(members),
            "expected_baseline": _team.common_access(members),
        })
    OUT.write_text(json.dumps({"_comment": __doc__.strip().splitlines()[0], "cases": cases}, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
