"""Pure business rules shared by both deployments (and mirrored in the plugin)."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .config import Config

TYPE_LABELS = {"ACCESS_PROFILE": "Access profile", "ROLE": "Role", "ENTITLEMENT": "Entitlement"}

# SailPoint limits on a generic approval task's text fields.
APPROVAL_NAME_MAX = 50
APPROVAL_DESCRIPTION_MAX = 150
APPROVAL_COMMENT_MAX = 150
# Soft limit the plugin applies for a tidy approval comment ("<INC>: <justification>").
# Not enforced by the Launcher form: a MAX_LENGTH rule on a form textarea breaks submission,
# and workflow-created approvals accept longer comments (225 characters verified live).
JUSTIFICATION_MAX = APPROVAL_COMMENT_MAX - len("INC0000000: ")   # 138


def inc_is_valid(cfg: Config, value: str | None) -> bool:
    return bool(value) and re.search(cfg.inc_pattern, value.strip()) is not None


def validate_request(cfg: Config, *, requester_id: str, approver_id: str, people: list[str],
                     items: list[dict[str, Any]], inc: str) -> list[str]:
    """Everything wrong with a bulk request, as sentences (empty list = OK)."""
    problems = []
    if not people:
        problems.append("Choose at least one person.")
    if cfg.people_max is not None and len(set(people)) > cfg.people_max:
        problems.append(f"Choose at most {cfg.people_max} people.")
    if not items:
        problems.append("Choose at least one access item.")
    if len(items) > cfg.catalog_max_items:
        problems.append(f"Choose at most {cfg.catalog_max_items} access items.")
    if any(i.get("type") not in cfg.catalog_types for i in items):
        problems.append("One of the chosen items is not an allowed type.")
    if not approver_id:
        problems.append("Choose an approver.")
    elif approver_id == requester_id:
        # SailPoint reassigns self-approvals to another admin, so refuse up front.
        problems.append("The approver must be someone other than you.")
    if not inc_is_valid(cfg, inc):
        problems.append(cfg.inc_message)
    return problems


def clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def catalog_options(cfg: Config, requestable: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Form SELECT options from /v3/requestable-objects, filtered by the config.

    Each option's value is the complete access object ({id, type, name}), which is
    exactly what the workflow's Manage Access step needs -- so the workflow never has
    to rebuild objects from bare IDs.
    """
    options = []
    own = f"{cfg.base_name} - Launcher Access"   # the profile that grants this tool; never offer it
    for obj in requestable:
        if obj.get("name") == own:
            continue
        kind = obj.get("type")
        name = obj.get("name") or obj.get("id")
        if kind not in cfg.catalog_types:
            continue
        if cfg.catalog_name_starts_with and not str(name).startswith(cfg.catalog_name_starts_with):
            continue
        source = (obj.get("source") or {}).get("name") if isinstance(obj.get("source"), dict) else None
        sub = TYPE_LABELS.get(kind, kind) + (f" · {source}" if source else "")
        options.append({"label": name, "subLabel": sub, "value": {"id": obj["id"], "type": kind, "name": name}})
    return sorted(options, key=lambda o: (o["label"].lower(), o["value"]["type"]))
