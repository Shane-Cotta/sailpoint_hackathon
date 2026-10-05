"""The shared flag cases must hold for the Python reference implementation.

shared/team-flag-cases.json is also run by the Team Access Radar UI plugin's
TypeScript tests, so if this passes and they pass, the MCP tools and the
in-product page give the same answer. Regenerate with shared/make_flag_cases.py.
"""

import json
from pathlib import Path

import pytest

from sailpoint_mcp.tools import _team

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "shared" / "team-flag-cases.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_matches_shared_case(case):
    members = [_team.build_member(doc) for doc in case["documents"]]
    assert _team.team_flags(members) == case["expected_flags"]
    assert _team.common_access(members) == case["expected_baseline"]
