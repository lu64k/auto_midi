"""Runtime loader for the project-owned style/groove routing skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .style_catalog import catalog_snapshot


SKILL_ROOT = Path(__file__).resolve().parent / "agent_skills" / "route-drum-style-groove"


def build_routing_skill_context(ui_style: str | None, ui_groove: str | None) -> str:
    """Render stable skill rules plus the relevant live catalog."""

    snapshot = catalog_snapshot()
    rules = SKILL_ROOT.joinpath("SKILL.md").read_text(encoding="utf-8")
    style_locked = bool(ui_style and ui_style != "free")
    groove_locked = bool(ui_groove and ui_groove != "free")
    if style_locked:
        selected_styles = {ui_style: snapshot.styles[ui_style]}
    else:
        selected_styles = snapshot.styles
    catalog_context = {
        "catalog_version": snapshot.version,
        "catalog_hash": snapshot.content_hash,
        "routing_constraints": {
            "ui_style": ui_style or "free",
            "ui_groove": ui_groove or "free",
            "style_locked": style_locked,
            "groove_locked": groove_locked,
        },
        "styles": {
            style_name: {
                "identity": style.get("identity", ""),
                "default_groove": style["default_groove"],
                "grooves": {
                    groove_name: _routing_groove(groove)
                    for groove_name, groove in style["grooves"].items()
                },
            }
            for style_name, style in selected_styles.items()
        },
    }
    return rules + "\n\n## Live catalog and constraints\n\n" + json.dumps(
        catalog_context, ensure_ascii=False, separators=(",", ":")
    )


def routing_catalog_metadata() -> dict[str, Any]:
    snapshot = catalog_snapshot()
    return {"catalog_version": snapshot.version, "catalog_hash": snapshot.content_hash}


def _routing_groove(groove: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": groove.get("identity", ""),
        "energy_neutral": bool(groove.get("energy_neutral", True)),
        "anchor": groove.get("anchor"),
        "pulse": groove.get("pulse"),
        "meters": groove.get("meters", []),
    }
