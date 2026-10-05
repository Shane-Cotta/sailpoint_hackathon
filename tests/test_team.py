"""Unit tests for the team-review helpers -- no tenant or credentials required."""

import asyncio

import pytest
from mcp.server import MCPServer

from sailpoint_mcp import tools
from sailpoint_mcp.tools import _team
from sailpoint_mcp.tools.get_manager_pending_reviews import (
    as_dict,
    summarize_certification,
    summarize_request,
)


def _doc(id_, name, access=(), accounts=(), access_count=None, **extra):
    doc = {
        "id": id_,
        "displayName": name,
        "access": [
            {"id": f"{t}-{n}", "type": t, "name": n, **({"source": {"name": s}} if s else {}), **kw}
            for t, n, s, kw in access
        ],
        "accounts": list(accounts),
        **extra,
    }
    if access_count is not None:
        doc["accessCount"] = access_count
    return doc


ROLE = ("ROLE", "Sales Rep", None, {})
CRM = ("ENTITLEMENT", "crm-user", "Salesforce", {})


# --- summarize_access -------------------------------------------------------


def test_summarize_access_groups_by_kind_and_labels_entitlements_with_source():
    doc = _doc(
        "1",
        "Ann",
        access=[
            ROLE,
            ("ACCESS_PROFILE", "CRM Basic", "Salesforce", {}),
            CRM,
            ("ENTITLEMENT", "Domain Admins", "Active Directory", {"privileged": True}),
            ("UNKNOWN_KIND", "ignored", None, {}),
        ],
        accounts=[
            {"name": "ann", "source": {"name": "Active Directory"}},
            {"name": "ann2", "source": {"name": "Active Directory"}, "disabled": True},
            {"name": "root", "source": {"name": "Linux"}, "privileged": True},
        ],
    )
    access = _team.summarize_access(doc)

    assert access["roles"] == ["Sales Rep"]
    assert access["access_profiles"] == ["CRM Basic"]
    assert access["entitlements"] == ["Active Directory: Domain Admins", "Salesforce: crm-user"]
    assert access["privileged"] == ["Active Directory: Domain Admins", "Linux account: root"]
    assert access["accounts"] == {"Active Directory": 2, "Linux": 1}
    assert access["disabled_accounts"] == 1


def test_summarize_access_tolerates_missing_arrays():
    access = _team.summarize_access({"id": "x"})
    assert access["roles"] == [] and access["accounts"] == {}


def test_build_member_falls_back_to_counting_access():
    member = _team.build_member(_doc("1", "Ann", access=[ROLE, CRM]))
    assert member["access_count"] == 2


# --- team_flags --------------------------------------------------------------


def _team_of(*docs):
    return [_team.build_member(d) for d in docs]


def _types(flags, who):
    return {f["type"] for f in flags if f["identity"] == who}


def test_leaver_with_access_is_high_severity_and_sorted_first():
    members = _team_of(
        _doc("1", "Ann", access=[ROLE, CRM], access_count=2),
        _doc("2", "Bob", access=[ROLE], access_count=1, lifecycleState="terminated"),
    )
    flags = _team.team_flags(members)
    assert flags[0]["type"] == "leaver_risk"
    assert flags[0]["identity"] == "Bob"
    assert flags[0]["severity"] == "high"


def test_inactive_without_any_access_is_not_flagged():
    members = _team_of(_doc("2", "Bob", inactive=True, access_count=0))
    assert _team.team_flags(members) == []


def test_unique_access_and_outlier_need_three_people():
    admin = ("ENTITLEMENT", "Domain Admins", "AD", {})
    small = _team_of(
        _doc("1", "Ann", access=[ROLE], access_count=1),
        _doc("2", "Bob", access=[ROLE, admin], access_count=20),
    )
    assert "unique_access" not in _types(_team.team_flags(small), "Bob")
    assert "access_outlier" not in _types(_team.team_flags(small), "Bob")

    big = small + _team_of(_doc("3", "Cy", access=[ROLE], access_count=2))
    flags = _team.team_flags(big)
    assert {"unique_access", "access_outlier"} <= _types(flags, "Bob")
    unique = next(f for f in flags if f["type"] == "unique_access")
    assert unique["items"] == ["AD: Domain Admins"]


def test_outlier_requires_a_real_gap():
    # 4 vs a median of 2 is 2x but only 2 items apart -- not worth a flag.
    members = _team_of(
        _doc("1", "Ann", access=[ROLE], access_count=2),
        _doc("2", "Bob", access=[ROLE], access_count=2),
        _doc("3", "Cy", access=[ROLE], access_count=4),
    )
    assert "access_outlier" not in _types(_team.team_flags(members), "Cy")


def test_privileged_access_is_medium_when_peers_share_it():
    root = ("ENTITLEMENT", "root", "Linux", {"privileged": True})
    members = _team_of(_doc("1", "Ann", access=[root]), _doc("2", "Bob", access=[root]),
                       _doc("3", "Cy", access=[root]))
    flags = [f for f in _team.team_flags(members) if f["type"] == "privileged_access"]
    assert {f["severity"] for f in flags} == {"medium"}


def test_privileged_access_nobody_else_has_is_high():
    admin = ("ENTITLEMENT", "AccountsPayable", "AD", {"privileged": True})
    members = _team_of(
        _doc("1", "Ann", access=[ROLE]),
        _doc("2", "Bob", access=[ROLE, admin]),
        _doc("3", "Cy", access=[ROLE]),
    )
    flag = next(f for f in _team.team_flags(members) if f["type"] == "privileged_access")
    assert flag["severity"] == "high"
    assert flag["items"] == ["AD: AccountsPayable"]
    assert "no one else" in flag["reason"]


def test_no_roles_only_when_the_team_normally_uses_roles():
    # Nobody has roles (like the demo tenant): not worth flagging anyone.
    no_role_team = _team_of(_doc("1", "Ann", access=[CRM]), _doc("2", "Bob", access=[CRM]))
    assert not any(f["type"] == "no_roles" for f in _team.team_flags(no_role_team))

    # Most of the team has a role; the one without stands out.
    members = _team_of(
        _doc("1", "Ann", access=[ROLE, CRM]),
        _doc("2", "Bob", access=[ROLE, CRM]),
        _doc("3", "Cy", access=[CRM]),
    )
    assert _types(_team.team_flags(members), "Cy") == {"no_roles"}


def test_missing_baseline_flags_an_unprovisioned_member():
    base = [ROLE, CRM, ("ENTITLEMENT", "All_Users", "AD", {})]
    members = _team_of(
        *[_doc(str(i), f"P{i}", access=base) for i in range(5)],
        _doc("new", "Newbie", access=[]),
    )
    flag = next(f for f in _team.team_flags(members) if f["identity"] == "Newbie")
    assert flag["type"] == "missing_baseline"
    assert "Lacks 3 of the 3" in flag["reason"]
    assert not any(f["type"] == "missing_baseline" for f in _team.team_flags(members[:5]))


def test_empty_team_has_no_flags_or_baseline():
    assert _team.team_flags([]) == []
    assert _team.common_access([]) == []


def test_common_access_is_items_most_of_the_team_holds():
    members = _team_of(
        _doc("1", "Ann", access=[ROLE, CRM]),
        _doc("2", "Bob", access=[ROLE, CRM]),
        _doc("3", "Cy", access=[ROLE]),
    )
    baseline = _team.common_access(members)
    assert baseline[0] == {"access": "Sales Rep", "kind": "roles", "held_by": 3}
    assert {"access": "Salesforce: crm-user", "kind": "entitlements", "held_by": 2} in baseline


def test_roster_entry_lists_the_members_flag_types():
    root = ("ENTITLEMENT", "root", "Linux", {"privileged": True})
    members = _team_of(_doc("1", "Ann", access=[CRM, root]))
    flags = _team.team_flags(members)
    entry = _team.roster_entry(members[0], flags)
    assert entry["flags"] == ["privileged_access"]
    assert entry["entitlements"] == 2


# --- identity resolution -----------------------------------------------------


def test_pick_single_returns_the_only_hit():
    assert _team.pick_single("Ann", [{"id": "1"}]) == {"id": "1"}


def test_pick_single_prefers_an_exact_name_match():
    docs = [
        {"id": "1", "displayName": "Adam Kennedy"},
        {"id": "2", "displayName": "Adam Kennedy-Smith"},
    ]
    assert _team.pick_single("Adam Kennedy", docs)["id"] == "1"


def test_pick_single_reports_candidates_when_ambiguous():
    docs = [{"id": "1", "displayName": "Adam A"}, {"id": "2", "displayName": "Adam B"}]
    with pytest.raises(_team.IdentityNotResolved) as exc:
        _team.pick_single("Adam*", docs)
    assert [c["id"] for c in exc.value.payload["candidates"]] == ["1", "2"]


def test_pick_single_explains_no_match():
    with pytest.raises(_team.IdentityNotResolved) as exc:
        _team.pick_single("Nobody", [])
    assert "No identity matched" in exc.value.payload["error"]


def test_direct_reports_search_filters_on_manager_id_with_nested_access():
    search = _team.direct_reports_search("abc123")
    assert search.query.query == 'manager.id:"abc123"'
    assert search.include_nested is True
    assert "access.type" in search.query_result_filter.includes


# --- pending reviews shaping ---------------------------------------------------


def test_summarize_certification_reports_progress():
    cert = summarize_certification(
        {
            "id": "c1",
            "name": "Q4 Manager Review",
            "campaign": {"name": "Q4"},
            "decisionsMade": 3,
            "decisionsTotal": 12,
            "identitiesCompleted": 1,
            "identitiesTotal": 4,
            "due": "2026-10-31T00:00:00Z",
        }
    )
    assert cert["progress"] == "3/12 decisions (25%)"
    assert cert["identities"] == "1/4 reviewed"
    assert cert["campaign"] == "Q4"


def test_summarize_request_drops_empty_fields():
    req = summarize_request({"name": "Salesforce Admin", "state": "EXECUTING"}, "Bob")
    assert req == {"requested_for": "Bob", "access": "Salesforce Admin", "state": "EXECUTING"}


def test_as_dict_unwraps_anyof_models():
    class Inner:
        def to_dict(self):
            return {"id": "x"}

    class Wrapper:
        actual_instance = Inner()

    assert as_dict(Wrapper()) == {"id": "x"}
    assert as_dict({"id": "y"}) == {"id": "y"}


# --- registration --------------------------------------------------------------


NEW_TOOLS = {"review_team_access", "get_identity_access", "get_manager_pending_reviews"}


def test_new_tools_register_with_descriptions():
    mcp = MCPServer("test")
    registered = tools.register_all(mcp)
    assert NEW_TOOLS <= set(registered)
    assert "_team" not in registered

    listed = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    for name in NEW_TOOLS:
        assert listed[name].description
