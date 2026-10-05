"""notify_manager: input shaping and failure reporting -- no tenant required."""

import asyncio
import json

from mcp.server import MCPServer

from sailpoint_mcp import tools
from sailpoint_mcp.config import ConfigError
from sailpoint_mcp.tools import notify_manager as nm


def _call(mcp, args):
    result = asyncio.run(mcp.call_tool("notify_manager", args))
    result = result[1] if isinstance(result, tuple) else result
    payload = getattr(result, "structured_content", None) or json.loads(result.content[0].text)
    return payload.get("result", payload) if set(payload) == {"result"} else payload


def test_trigger_input_collapses_whitespace_and_caps_detail():
    data = nm.build_trigger_input("id1", " privileged_access (high) ", "line one\n  line two")
    assert data == {"identityId": "id1", "flag": "privileged_access (high)", "detail": "line one line two"}

    long = nm.build_trigger_input("id1", "x", "word " * 500)["detail"]
    assert len(long) == nm.MAX_DETAIL_CHARS and long.endswith("...")


def test_wait_for_execution_stops_at_a_final_status(monkeypatch):
    statuses = iter(["Running", "Completed"])
    monkeypatch.setattr(nm, "execution_status", lambda _id: next(statuses))
    monkeypatch.setattr(nm.time, "sleep", lambda _s: None)
    assert nm.wait_for_execution("e1", timeout=5) == "Completed"


def test_unconfigured_notifications_return_an_error_not_a_crash(monkeypatch):
    def missing():
        raise ConfigError("Manager notifications are not configured")

    monkeypatch.setattr(nm, "load_flagged_workflow", missing)
    mcp = MCPServer("test")
    tools.register_all(mcp)
    out = _call(mcp, {"identity": "Ann", "flag": "x", "detail": "y"})
    assert out["notified"] is False
    assert "not configured" in out["error"]


def test_no_manager_means_no_notification(monkeypatch):
    monkeypatch.setattr(nm, "load_flagged_workflow", lambda: ("wf", object()))
    monkeypatch.setattr(nm._team, "resolve_identity", lambda q: {"id": "1", "displayName": "Ann"})
    mcp = MCPServer("test")
    tools.register_all(mcp)
    out = _call(mcp, {"identity": "Ann", "flag": "x", "detail": "y"})
    assert out["notified"] is False
    assert "no manager" in out["error"]


def test_failed_workflow_is_reported_as_not_notified(monkeypatch):
    class Result:
        workflow_execution_id = "e1"

    monkeypatch.setattr(nm, "load_flagged_workflow", lambda: ("wf", object()))
    monkeypatch.setattr(
        nm._team,
        "resolve_identity",
        lambda q: {"id": "1", "displayName": "Ann", "manager": {"displayName": "Boss"}},
    )
    monkeypatch.setattr(nm, "call_sailpoint_as", lambda settings, op: Result())
    monkeypatch.setattr(nm, "wait_for_execution", lambda _id: "Failed")
    mcp = MCPServer("test")
    tools.register_all(mcp)
    out = _call(mcp, {"identity": "Ann", "flag": "x", "detail": "y"})
    assert out["notified"] is False
    assert out["workflow_status"] == "Failed"
    assert "no email was sent" in out["error"]
