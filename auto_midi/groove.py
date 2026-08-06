"""Dynamic style/groove views backed by the hot-reloadable catalog."""

from __future__ import annotations

from .style_catalog import DynamicCatalogMapping, catalog_snapshot, groove_data


GROOVES_BY_STYLE = DynamicCatalogMapping(
    lambda snapshot: {name: tuple(style["grooves"]) for name, style in snapshot.styles.items()}
)
DEFAULT_GROOVE_BY_STYLE = DynamicCatalogMapping(
    lambda snapshot: {name: style["default_groove"] for name, style in snapshot.styles.items()}
)
GROOVE_ANCHORS = DynamicCatalogMapping(
    lambda snapshot: {
        groove_name: groove["anchor"]
        for style in snapshot.styles.values()
        for groove_name, groove in style["grooves"].items()
    }
)
GROOVE_PULSES = DynamicCatalogMapping(
    lambda snapshot: {
        groove_name: groove["pulse"]
        for style in snapshot.styles.values()
        for groove_name, groove in style["grooves"].items()
        if groove.get("pulse") is not None
    }
)
GROOVE_PROFILES = DynamicCatalogMapping(
    lambda snapshot: {
        groove_name: groove["profile"]
        for style in snapshot.styles.values()
        for groove_name, groove in style["grooves"].items()
    }
)


def grooves_for_style(style: str, include_free: bool = False) -> tuple[str, ...]:
    grooves = tuple(catalog_snapshot().styles.get(style, {}).get("grooves", {}))
    if not grooves:
        return ("free",)
    if include_free and "free" not in grooves:
        return ("free", *grooves)
    return grooves


def default_groove(style: str) -> str:
    return str(catalog_snapshot().styles.get(style, {}).get("default_groove", "free"))


def groove_identity(groove: str) -> str:
    data = groove_data(groove)
    return str(data.get("identity", groove)) if data else groove
