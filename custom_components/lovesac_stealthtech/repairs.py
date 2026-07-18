"""Repairs nudge for unknown enum values (v0.3 D5).

When a raw layout / arm-type / covering sensor reports a value that is not in
the shipped enum table AND the operator has not set a local override, raise a
dismissible, non-fixable Repairs issue whose learn-more link deep-links the
GitHub enum-report issue form with the raw values prefilled.

- `async_create_issue` kwargs verified against HA core 2024.11.0
  homeassistant/helpers/issue_registry.py (is_fixable, is_persistent,
  severity, translation_key, translation_placeholders, learn_more_url).
- GitHub issue FORMS support prefilling via URL query parameters named after
  the form field ids, plus `template=` and `title=`
  (docs.github.com: "Creating an issue from a URL query"). The field ids
  below match .github/ISSUE_TEMPLATE/enum_report.yml.
"""
from __future__ import annotations

from urllib.parse import urlencode

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import protocol
from .const import (
    CONF_MY_ARM_STYLE,
    CONF_MY_COUCH_SHAPE,
    CONF_MY_FABRIC,
    DOMAIN,
)

ISSUE_TEMPLATE_URL = (
    "https://github.com/ojiudezue/ha-lovesac-stealthtech/issues/new"
)

# (state attr, human kind, shipped table, override option key, form field id)
ENUM_KINDS: tuple[tuple[str, str, dict[int, str], str, str], ...] = (
    ("layout", "layout", protocol.LAYOUT_NAMES, CONF_MY_COUCH_SHAPE, "raw_layout"),
    ("arm_type", "arm type", protocol.ARM_TYPE_NAMES, CONF_MY_ARM_STYLE, "raw_arm_type"),
    ("covering", "covering", protocol.COVERING_NAMES, CONF_MY_FABRIC, "raw_covering"),
)


def prefilled_report_url(field_id: str, value: int, versions: dict[str, str]) -> str:
    """Deep-link the enum-report issue form with the observed values."""
    params = {
        "template": "enum_report.yml",
        "title": f"Enum report: {field_id} = {value}",
        field_id: str(value),
    }
    if versions:
        params["firmware_versions"] = " / ".join(
            f"{k} {v}" for k, v in sorted(versions.items())
        )
    return f"{ISSUE_TEMPLATE_URL}?{urlencode(params)}"


def async_check_unknown_enums(hass: HomeAssistant, coordinator) -> None:
    """Raise one dismissible Repairs issue per unknown (kind, value).

    Suppressed when the shipped table already maps the value or the operator
    has set the corresponding local override.
    """
    options = getattr(coordinator.config_entry, "options", None) or {}
    state = coordinator.state
    for attr, kind, table, override_key, field_id in ENUM_KINDS:
        raw = getattr(state, attr)
        # A-3 / B-LOW-1: retract previously-raised issues that are now
        # suppressed — the operator set the local override, or a shipped
        # table update now maps the reported value.
        # `async_delete_issue(hass, domain, issue_id)` signature verified
        # against HA core 2024.11.0 helpers/issue_registry.py.
        prefix = f"unknown_enum_{attr}_"
        for issue_id in [
            i for i in coordinator.reported_enum_issues if i.startswith(prefix)
        ]:
            value = int(issue_id[len(prefix):])
            if options.get(override_key) or value in table:
                ir.async_delete_issue(hass, DOMAIN, issue_id)
                coordinator.reported_enum_issues.discard(issue_id)
        if raw is None or raw in table or options.get(override_key):
            continue
        issue_id = f"unknown_enum_{attr}_{raw}"
        if issue_id in coordinator.reported_enum_issues:
            continue
        coordinator.reported_enum_issues.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,  # dismissible nudge; no fix flow
            severity=ir.IssueSeverity.WARNING,
            translation_key="unknown_enum_value",
            translation_placeholders={"kind": kind, "value": str(raw)},
            learn_more_url=prefilled_report_url(field_id, raw, state.versions),
        )


def async_delete_tracked_issues(hass: HomeAssistant, coordinator) -> None:
    """Retract every Repairs issue this coordinator raised (entry unload).

    B-LOW-1: without this, an unloaded/removed entry leaves its unknown-enum
    nudges orphaned in the issue registry.
    """
    for issue_id in coordinator.reported_enum_issues:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    coordinator.reported_enum_issues.clear()
