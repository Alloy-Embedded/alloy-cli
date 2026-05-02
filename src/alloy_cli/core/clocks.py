"""Operations on the ``[clocks]`` section of ``alloy.toml``.

Clock *profiles* are named bundles of source / divider / PLL settings
that the user can dial in via the TUI Clock Tree screen and persist
back to ``alloy.toml`` under ``[clocks.profiles.<name>]``.

This module is the single seam every façade (TUI, MCP, future CLI)
goes through.  Each operation is pure: it consumes a
:class:`ProjectConfig` + parameters and emits a :class:`UnifiedDiff`
that the caller writes to disk.

The actual PLL M/N/R algebra (translating a target SYSCLK into
vendor-specific RCC settings) lives in alloy-codegen.  This module
deliberately treats the body as an open dictionary of well-known
fields plus an ``extras`` map; the codegen consumer interprets it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alloy_cli.core.diagnostics import FilePatch, UnifiedDiff
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UnknownProfileError(AlloyCliError):
    """``[clocks].profile`` references a name that isn't in ``profiles``."""

    error_type = "unknown-clock-profile"


class DuplicateProfileError(AlloyCliError):
    """A profile name already exists in ``[clocks].profiles``."""

    error_type = "duplicate-clock-profile"


class InvalidProfileNameError(AlloyCliError):
    """Profile name is empty or doesn't match ``[a-zA-Z][a-zA-Z0-9_]*``."""

    error_type = "invalid-clock-profile-name"


# ---------------------------------------------------------------------------
# Profile body
# ---------------------------------------------------------------------------


# Canonical clock-node identifiers we know how to map onto the
# typed fields of a profile body.  Anything else lands in
# ``extras`` so vendor-specific overrides round-trip losslessly.
_KNOWN_FIELDS = ("pll_n", "pll_r", "sysclk_hz", "hclk_div", "apb1_div", "apb2_div")
_NODE_TO_FIELD = {
    "PLL_N": "pll_n",
    "PLL_R": "pll_r",
    "SYSCLK": "sysclk_hz",
}


@dataclass(frozen=True, slots=True)
class ClockProfileBody:
    """One named clock profile.

    Fields map onto the well-known knobs every supported MCU has
    (source oscillator, PLL N/R, SYSCLK target, AHB / APB dividers).
    Vendor-specific extras flow through :attr:`extras` so the file
    round-trips losslessly.
    """

    source: str
    pll_n: int | None = None
    pll_r: int | None = None
    sysclk_hz: int | None = None
    hclk_div: int | None = None
    apb1_div: int | None = None
    apb2_div: int | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a TOML-friendly dict.

        Keys are emitted in a stable order: ``source`` first, then the
        well-known fields in declaration order, then any extras.
        Optional fields whose value is ``None`` are dropped so the
        emitted TOML stays compact.
        """
        body: dict[str, Any] = {"source": self.source}
        for name in _KNOWN_FIELDS:
            value = getattr(self, name)
            if value is not None:
                body[name] = value
        for key, value in self.extras.items():
            if key in body or key == "source":
                continue
            body[key] = value
        return body


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def profile_from_rates(rates: Mapping[str, int]) -> ClockProfileBody:
    """Derive a :class:`ClockProfileBody` from an in-screen override map.

    The override map is the ``Mapping[node_id, rate_hz]`` that
    :class:`ClockTreeWidget` accumulates as the user dials in
    overrides.  We extract the well-known node ids (``SYSCLK``,
    ``PLL_N``, ``PLL_R``) into the typed fields and pass everything
    else through as extras.

    The ``source`` field is heuristic: ``HSE`` if an ``HSE`` rate is
    present, ``PLL`` if any PLL knob is overridden, otherwise
    ``HSI`` so simple low-power profiles default sensibly.
    """
    source = "HSI"
    if "HSE" in rates:
        source = "HSE"
    elif any(key in rates for key in ("PLL", "PLL_R", "PLL_N")):
        source = "PLL"

    typed: dict[str, int] = {}
    extras: dict[str, int] = {}
    for node_id, rate in rates.items():
        field_name = _NODE_TO_FIELD.get(node_id)
        if field_name is not None:
            typed[field_name] = int(rate)
        else:
            extras[node_id] = int(rate)

    return ClockProfileBody(
        source=source,
        pll_n=typed.get("pll_n"),
        pll_r=typed.get("pll_r"),
        sysclk_hz=typed.get("sysclk_hz"),
        hclk_div=typed.get("hclk_div"),
        apb1_div=typed.get("apb1_div"),
        apb2_div=typed.get("apb2_div"),
        extras=extras,
    )


# ---------------------------------------------------------------------------
# Diff-emitting operations
# ---------------------------------------------------------------------------


def save_profile(
    config: ProjectConfig, name: str, body: ClockProfileBody
) -> UnifiedDiff:
    """Emit the diff that adds (or updates) a named clock profile.

    Raises :class:`InvalidProfileNameError` for empty or
    syntactically-invalid names.  Existing profiles with the same
    name are *replaced* — callers wanting strict create-only semantics
    should check the existing config before invoking.
    """
    _validate_name(name)

    new_clocks = dict(config.clocks)
    profiles = dict(new_clocks.get("profiles") or {})
    profiles[name] = body.to_dict()
    new_clocks["profiles"] = profiles

    return _diff(config, new_clocks)


def activate_profile(config: ProjectConfig, name: str) -> UnifiedDiff:
    """Emit the diff that flips ``[clocks].profile`` to ``name``.

    Raises :class:`UnknownProfileError` when ``name`` isn't already
    defined under ``[clocks].profiles`` — activation never silently
    creates an empty profile.
    """
    profiles = dict(config.clocks.get("profiles") or {})
    if name not in profiles:
        known = ", ".join(sorted(profiles)) if profiles else "(none)"
        raise UnknownProfileError(
            f"Clock profile {name!r} is not defined in [clocks].profiles "
            f"(known: {known})."
        )

    new_clocks = dict(config.clocks)
    new_clocks["profile"] = name
    return _diff(config, new_clocks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> None:
    if not name or not name.strip():
        raise InvalidProfileNameError("Profile name must not be empty.")
    cleaned = name.strip()
    if not cleaned[0].isalpha():
        raise InvalidProfileNameError(
            f"Profile name {cleaned!r} must start with a letter."
        )
    for ch in cleaned[1:]:
        if not (ch.isalnum() or ch == "_"):
            raise InvalidProfileNameError(
                f"Profile name {cleaned!r} contains invalid character {ch!r}."
            )


def _diff(config: ProjectConfig, new_clocks: dict[str, Any]) -> UnifiedDiff:
    new_config = ProjectConfig(
        schema_version=config.schema_version,
        project=config.project,
        board=config.board,
        chip=config.chip,
        clocks=new_clocks,
        peripherals=config.peripherals,
        build=config.build,
        flash=config.flash,
        raw=config.raw,
    )
    # ``core.project.dumps`` is the single canonical TOML emitter.
    from alloy_cli.core.project import dumps as _dumps

    return UnifiedDiff(
        patches=(
            FilePatch(
                path=Path(PROJECT_FILE),
                before=_dumps(config),
                after=_dumps(new_config),
            ),
        )
    )


__all__ = [
    "ClockProfileBody",
    "DuplicateProfileError",
    "InvalidProfileNameError",
    "UnknownProfileError",
    "activate_profile",
    "profile_from_rates",
    "save_profile",
]
