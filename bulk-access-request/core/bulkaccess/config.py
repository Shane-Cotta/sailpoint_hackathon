"""Load and validate a tenant config file (see config/bulk-access.example.json).

Everything tenant-specific lives in that JSON file or in the environment, so the
same code installs into any Identity Security Cloud tenant. Credentials are never
read from the config itself: SAIL_BASE_URL / SAIL_CLIENT_ID / SAIL_CLIENT_SECRET
come from the environment or from the .env file the config names.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODES = ("dry-run", "live")
ITEM_TYPES = ("ACCESS_PROFILE", "ROLE", "ENTITLEMENT")
TIMEOUT_ACTIONS = ("EXPIRED", "APPROVED")
PRIORITIES = ("LOW", "MEDIUM", "HIGH")


class ConfigError(ValueError):
    """The config file is missing or invalid; the message says what to fix."""


@dataclass(frozen=True)
class Config:
    prefix: str
    mode: str
    inc_pattern: str
    inc_example: str
    inc_message: str
    catalog_types: tuple[str, ...]
    catalog_name_starts_with: str | None
    catalog_max_items: int
    people_max: int
    approval_timeout_days: int
    approval_action_at_timeout: str
    approval_priority: str
    override_recipients: tuple[str, ...]
    cc_approver: bool
    owner_id: str | None
    plugin_alias: str
    plugin_display_name: str
    launcher_access_approval: str = "MANAGER"
    env_file: str | None = None
    source_path: str | None = field(default=None, compare=False)

    # Every object we create is named from the prefix, so a tenant can host several
    # independent copies (and so other teams can tell ours apart).
    @property
    def base_name(self) -> str:
        return f"{self.prefix} Bulk Access Request".strip()

    @property
    def form_name(self) -> str:
        return f"{self.base_name} Form"

    @property
    def launcher_workflow_name(self) -> str:
        return self.base_name

    @property
    def plugin_workflow_name(self) -> str:
        return f"{self.base_name} (Plugin)"

    @property
    def launcher_name(self) -> str:
        return self.base_name

    @property
    def live(self) -> bool:
        return self.mode == "live"


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ConfigError(message)


def from_dict(data: dict[str, Any], source_path: str | None = None) -> Config:
    inc = data.get("inc") or {}
    catalog = data.get("catalog") or {}
    people = data.get("people") or {}
    approval = data.get("approval") or {}
    notes = data.get("notifications") or {}
    plugin = data.get("plugin") or {}

    prefix = str(data.get("prefix", "")).strip()
    _require(bool(prefix), "`prefix` is required (e.g. \"UCSF\"); it names every object created in the tenant.")
    _require(len(prefix) <= 20, "`prefix` must be 20 characters or fewer.")

    mode = data.get("mode", "dry-run")
    _require(mode in MODES, f"`mode` must be one of {MODES}, got {mode!r}.")

    pattern = inc.get("pattern", r"^INC\d{7}$")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ConfigError(f"`inc.pattern` is not a valid regular expression: {exc}") from exc
    example = inc.get("example", "INC0012345")
    _require(re.search(pattern, example) is not None, f"`inc.example` ({example!r}) does not match `inc.pattern`.")

    types = tuple(catalog.get("types") or ITEM_TYPES)
    _require(all(t in ITEM_TYPES for t in types), f"`catalog.types` may only contain {ITEM_TYPES}.")

    max_items = int(catalog.get("maxItems", 25))
    _require(1 <= max_items <= 25, "`catalog.maxItems` must be between 1 and 25 (SailPoint's per-request limit).")
    people_max = int(people.get("max", 50))
    _require(1 <= people_max <= 250, "`people.max` must be between 1 and 250.")

    timeout = int(approval.get("timeoutDays", 7))
    _require(1 <= timeout <= 90, "`approval.timeoutDays` must be between 1 and 90.")
    at_timeout = approval.get("actionAtTimeout", "EXPIRED")
    _require(at_timeout in TIMEOUT_ACTIONS, f"`approval.actionAtTimeout` must be one of {TIMEOUT_ACTIONS}.")
    priority = approval.get("priority", "MEDIUM")
    _require(priority in PRIORITIES, f"`approval.priority` must be one of {PRIORITIES}.")

    recipients = tuple(notes.get("overrideRecipients") or ())
    _require(all("@" in r for r in recipients), "`notifications.overrideRecipients` must be email addresses.")

    launcher = data.get("launcher") or {}
    access_approval = launcher.get("accessApproval", "MANAGER")
    _require(access_approval in ("MANAGER", "NONE"), "`launcher.accessApproval` must be \"MANAGER\" or \"NONE\".")

    alias = plugin.get("alias") or f"{prefix.lower()}-bulk-access"
    _require(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}", alias) is not None,
             "`plugin.alias` must be lowercase letters, digits and dashes.")

    return Config(
        prefix=prefix,
        mode=mode,
        inc_pattern=pattern,
        inc_example=example,
        inc_message=inc.get("message") or f"Enter a ServiceNow incident number, e.g. {example}.",
        catalog_types=types,
        catalog_name_starts_with=catalog.get("nameStartsWith") or None,
        catalog_max_items=max_items,
        people_max=people_max,
        approval_timeout_days=timeout,
        approval_action_at_timeout=at_timeout,
        approval_priority=priority,
        override_recipients=recipients,
        cc_approver=bool(notes.get("ccApprover", True)),
        owner_id=data.get("owner") or None,
        plugin_alias=alias,
        plugin_display_name=plugin.get("displayName") or f"{prefix} Bulk Access Request",
        launcher_access_approval=access_approval,
        env_file=data.get("envFile") or None,
        source_path=source_path,
    )


def load(path: str | os.PathLike[str]) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(
            f"Config file {p} not found. Copy config/bulk-access.example.json to config/<tenant>.json and edit it."
        )
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{p} is not valid JSON: {exc}") from exc
    return from_dict(data, source_path=str(p))
