"""Core unit tests: config validation, rules, and the generated definitions. No tenant needed."""

import json
from pathlib import Path

import pytest

from bulkaccess import config, definitions, rules

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "bulk-access.example.json"


def cfg_with(**overrides):
    data = json.loads(EXAMPLE.read_text())
    for dotted, value in overrides.items():
        target = data
        *parents, leaf = dotted.split("__")
        for part in parents:
            target = target.setdefault(part, {})
        target[leaf] = value
    return config.from_dict(data)


# ── config ────────────────────────────────────────────────────────────────────
def test_example_config_loads_in_dry_run():
    cfg = config.load(EXAMPLE)
    assert cfg.prefix == "UCSF" and cfg.mode == "dry-run" and not cfg.live
    assert cfg.form_name == "UCSF Bulk Access Request Form"
    assert cfg.plugin_workflow_name == "UCSF Bulk Access Request (Plugin)"


@pytest.mark.parametrize("key,value,fragment", [
    ("prefix", "", "prefix"),
    ("mode", "yolo", "mode"),
    ("inc__pattern", "([", "regular expression"),
    ("inc__example", "CHG123", "does not match"),
    ("catalog__types", ["GROUP"], "catalog.types"),
    ("catalog__maxItems", 26, "maxItems"),
    ("approval__timeoutDays", 0, "timeoutDays"),
    ("notifications__overrideRecipients", ["not-an-email"], "email"),
    ("plugin__alias", "Has Spaces", "alias"),
])
def test_bad_config_is_rejected_with_a_useful_message(key, value, fragment):
    with pytest.raises(config.ConfigError, match=fragment):
        cfg_with(**{key: value})


def test_missing_config_file_explains_what_to_do(tmp_path):
    with pytest.raises(config.ConfigError, match="Copy config/bulk-access.example.json"):
        config.load(tmp_path / "nope.json")


# ── rules ─────────────────────────────────────────────────────────────────────
def test_inc_validation_uses_the_configured_pattern():
    cfg = config.load(EXAMPLE)
    assert rules.inc_is_valid(cfg, "INC0012345")
    assert not rules.inc_is_valid(cfg, "INC12345")
    assert not rules.inc_is_valid(cfg, "")
    custom = cfg_with(inc__pattern=r"^(INC|RITM)\d{7}$", inc__example="RITM0000001")
    assert rules.inc_is_valid(custom, "RITM0000001")


def test_validate_request_lists_every_problem():
    cfg = config.load(EXAMPLE)
    problems = rules.validate_request(cfg, requester_id="me", approver_id="me", people=[], items=[], inc="nope")
    assert "Choose at least one person." in problems
    assert "Choose at least one access item." in problems
    assert "The approver must be someone other than you." in problems
    assert cfg.inc_message in problems
    ok = rules.validate_request(cfg, requester_id="me", approver_id="boss", people=["p1"],
                                items=[{"id": "a", "type": "ACCESS_PROFILE"}], inc="INC0012345")
    assert ok == []


def test_catalog_options_carry_full_access_objects_and_respect_filters():
    cfg = cfg_with(catalog__types=["ACCESS_PROFILE"], catalog__nameStartsWith="UCSF")
    opts = rules.catalog_options(cfg, [
        {"id": "1", "type": "ACCESS_PROFILE", "name": "UCSF Bulk Test Access", "source": {"name": "UCSF SaaS"}},
        {"id": "2", "type": "ACCESS_PROFILE", "name": "Sales Regional - AD"},
        {"id": "3", "type": "ROLE", "name": "UCSF Role"},
    ])
    assert opts == [{"label": "UCSF Bulk Test Access", "subLabel": "Access profile · UCSF SaaS",
                     "value": {"id": "1", "type": "ACCESS_PROFILE", "name": "UCSF Bulk Test Access"}}]


# ── definitions ───────────────────────────────────────────────────────────────
def _form_elements(form):
    return {e["key"]: e for e in form["formElements"][0]["config"]["formElements"]}


def test_form_enforces_inc_regex_and_required_fields():
    cfg = config.load(EXAMPLE)
    els = _form_elements(definitions.bulk_form(cfg, "owner", []))
    assert set(els) == {"people", "items", "approver", "inc", "justification"}
    regex = next(v for v in els["inc"]["validations"] if v["validationType"] == "REGEX")
    assert regex["config"] == {"regex": cfg.inc_pattern, "message": cfg.inc_message}   # shape SailPoint accepts
    assert els["approver"]["config"]["maximum"] == 1
    assert els["items"]["config"]["dataSource"]["dataSourceType"] == "STATIC"


def _steps(wf):
    return wf["definition"]["steps"]


def test_dry_run_never_requests_access_and_live_does():
    dry = definitions.bulk_workflow(config.load(EXAMPLE), variant="launcher", owner_id="o", form_id="f")
    assert "Request Access" not in _steps(dry)
    assert "DRY RUN" in json.dumps(_steps(dry)["Email Approved"])
    live = definitions.bulk_workflow(cfg_with(mode="live"), variant="launcher", owner_id="o", form_id="f")
    loop = _steps(live)["Request Access"]["attributes"]
    assert loop["input.$"] == "$.interactiveForm.formData.people"      # one iteration per person
    assert loop["context.$"] == "$"                                    # steps in a loop only see $.loop.*
    manage = loop["steps"]["Manage Access"]["attributes"]
    assert manage["addIdentities.$"] == "$.loop.loopInput"
    assert manage["requestedItems.$"] == "$.loop.context.interactiveForm.formData.items"   # all items per request
    assert "{{$.loop.context.interactiveForm.formData.inc}}" in manage["comments"]


def test_approval_goes_to_the_chosen_approver_and_branches_on_status():
    for variant, approver_path in (("launcher", "$.interactiveForm.formData.approver"), ("plugin", "$.trigger.approverId")):
        wf = definitions.bulk_workflow(cfg_with(mode="live"), variant=variant, owner_id="o", form_id="f")
        approval = _steps(wf)["Bulk Approval"]["attributes"]
        assert approval["approvalType"] == "SINGLE" and approval["singleApproverCategory"] == "IDENTITY"
        assert approval["singleApproverIdentityId.$"] == approver_path
        choice = _steps(wf)["Approved?"]["choiceList"][0]
        assert choice["variableA.$"] == "$.bulkApproval.status" and choice["nextStep"] == "Request Access"
        assert _steps(wf)["Approved?"]["defaultStep"] == "Email Denied"


def test_launcher_trigger_is_scoped_to_its_own_workflow():
    wf = definitions.bulk_workflow(config.load(EXAMPLE), variant="launcher", owner_id="o", form_id="f", workflow_id="w-123")
    assert wf["trigger"]["attributes"]["id"] == "idn:interactive-process-launched"
    assert wf["trigger"]["attributes"]["filter.$"] == "$[?(@.workflowId == 'w-123')]"


def test_plugin_variant_is_external_and_disabled():
    wf = definitions.bulk_workflow(config.load(EXAMPLE), variant="plugin", owner_id="o")
    assert wf["trigger"]["type"] == "EXTERNAL" and wf["enabled"] is False
    assert "Interactive Form" not in _steps(wf)


def test_demo_tenants_can_redirect_all_email():
    cfg = cfg_with(notifications__overrideRecipients=["demo@example.com"])
    wf = definitions.bulk_workflow(cfg, variant="launcher", owner_id="o", form_id="f")
    for name in ("Email Approved", "Email Denied"):
        attrs = _steps(wf)[name]["attributes"]
        assert attrs["recipientEmailList"] == ["demo@example.com"] and "carbonCopy.$" not in attrs


def test_every_next_step_exists():
    wf = definitions.bulk_workflow(cfg_with(mode="live"), variant="launcher", owner_id="o", form_id="f")
    steps = _steps(wf)
    targets = {s.get("nextStep") for s in steps.values()} | {s.get("defaultStep") for s in steps.values()}
    targets |= {c["nextStep"] for s in steps.values() for c in s.get("choiceList", [])}
    assert {t for t in targets if t} <= set(steps)
    assert wf["definition"]["start"] in steps


def test_another_tenant_gets_its_own_names():
    other = cfg_with(prefix="ACME", plugin__alias="acme-bulk")
    assert definitions.bulk_form(other, "o", [])["name"] == "ACME Bulk Access Request Form"
    assert definitions.bulk_workflow(other, variant="plugin", owner_id="o")["name"] == "ACME Bulk Access Request (Plugin)"
    assert definitions.bulk_launcher(other, "w")["name"] == "ACME Bulk Access Request"


# ── lessons from the live tenant ──────────────────────────────────────────────
def test_form_people_picker_is_capped_at_sailpoints_30_selection_limit():
    cfg = cfg_with(people__max=100)
    els = _form_elements(definitions.bulk_form(cfg, "o", []))
    assert els["people"]["config"]["maximum"] == definitions.FORM_SELECT_MAX == 30


def test_catalog_never_offers_the_profile_that_grants_the_tool_itself():
    cfg = cfg_with(catalog__nameStartsWith="UCSF")
    opts = rules.catalog_options(cfg, [
        {"id": "1", "type": "ACCESS_PROFILE", "name": "UCSF Bulk Access Request - Launcher Access"},
        {"id": "2", "type": "ACCESS_PROFILE", "name": "UCSF Bulk Test Access"},
    ])
    assert [o["label"] for o in opts] == ["UCSF Bulk Test Access"]


def test_launcher_access_profile_wraps_the_assigned_launchers_entitlement():
    ent = {"id": "e1", "name": "UCSF Bulk Access Request", "source": {"id": "s1", "name": "IdentityNow"}}
    ap = definitions.launcher_access_profile(config.load(EXAMPLE), "o", ent)
    assert ap["name"] == "UCSF Bulk Access Request - Launcher Access"
    assert ap["requestable"] is True and ap["entitlements"] == [{"id": "e1", "type": "ENTITLEMENT", "name": "UCSF Bulk Access Request"}]
    assert ap["source"]["id"] == "s1"
    assert ap["accessRequestConfig"]["approvalSchemes"] == [{"approverType": "MANAGER"}]
    no_approval = definitions.launcher_access_profile(cfg_with(launcher__accessApproval="NONE"), "o", ent)
    assert no_approval["accessRequestConfig"]["approvalSchemes"] == []


def test_failure_end_step_has_the_fields_the_validator_requires():
    wf = definitions.bulk_workflow(config.load(EXAMPLE), variant="launcher", owner_id="o", form_id="f")
    end = _steps(wf)["End Step - Rejected"]
    assert end["type"] == "failure" and end["failureName"] and end["description"] and "attributes" not in end


def test_launcher_form_has_no_length_rule_on_the_justification():
    # A MAX_LENGTH validation on a form TEXTAREA silently stops submissions reaching the
    # workflow (found live), so the form must not have one.
    els = _form_elements(definitions.bulk_form(config.load(EXAMPLE), "o", []))
    assert [v["validationType"] for v in els["justification"]["validations"]] == ["REQUIRED"]
