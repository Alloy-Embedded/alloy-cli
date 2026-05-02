"""``alloy flash`` orchestration.

Talks to ``probe-rs`` for probe enumeration + run, with an OpenOCD
fallback when the project's ``alloy.toml [flash].openocd_config``
points at a config file.  Tests inject a :class:`process.FakeRunner`
to avoid real hardware.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from alloy_cli.core import process
from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.errors import AlloyCliError, BoardNotFoundError, ToolchainMissingError
from alloy_cli.core.events import record_event
from alloy_cli.core.project import AlloyDir, ProjectConfig


@dataclass(frozen=True, slots=True)
class ProbeInfo:
    """One debug probe enumerated by ``probe-rs list``."""

    kind: str  # "stlink", "jlink", "cmsis-dap", "picoprobe", …
    serial: str | None
    vendor_id: int | None
    product_id: int | None
    label: str  # human-friendly description

    @property
    def short(self) -> str:
        sn = f" sn={self.serial}" if self.serial else ""
        return f"{self.kind}{sn} ({self.label})"


class ProbeNotFoundError(AlloyCliError):
    error_type = "probe-not-found"


class MultipleProbesError(AlloyCliError):
    error_type = "multiple-probes"


@dataclass(frozen=True, slots=True)
class FlashResult:
    """Outcome of ``probe-rs run`` / ``openocd``."""

    probe: ProbeInfo
    elf: Path
    returncode: int
    log: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# ---------------------------------------------------------------------------
# Probe enumeration
# ---------------------------------------------------------------------------


_PLAIN_LINE = re.compile(
    r"\[\d+\]\s*:\s*(?P<label>[^\n]+?)\s*--\s*(?P<vid>[0-9a-f]+):(?P<pid>[0-9a-f]+)"
    r"(?:\s*\(serial:\s*(?P<serial>[^)]+)\))?",
    re.IGNORECASE,
)


def _parse_probe_rs_json(text: str) -> tuple[ProbeInfo, ...]:
    """Parse ``probe-rs list --output=json`` output."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ()
    items = payload if isinstance(payload, list) else payload.get("probes") or []
    out: list[ProbeInfo] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("kind") or item.get("probe_type") or "probe")
        out.append(
            ProbeInfo(
                kind=kind.lower(),
                serial=item.get("serial_number") or item.get("serial"),
                vendor_id=item.get("vendor_id") or item.get("vid"),
                product_id=item.get("product_id") or item.get("pid"),
                label=str(item.get("identifier") or item.get("name") or kind),
            )
        )
    return tuple(out)


def _classify_probe_label(label: str) -> str:
    lowered = label.lower()
    if "j-link" in lowered or "jlink" in lowered:
        return "jlink"
    if "st-link" in lowered or "stlink" in lowered:
        return "stlink"
    if "cmsis-dap" in lowered or "cmsisdap" in lowered:
        return "cmsis-dap"
    if "picoprobe" in lowered:
        return "picoprobe"
    return "probe"


def _parse_probe_rs_plain(text: str) -> tuple[ProbeInfo, ...]:
    out: list[ProbeInfo] = []
    for match in _PLAIN_LINE.finditer(text):
        label = match.group("label").strip()
        kind = _classify_probe_label(label)
        out.append(
            ProbeInfo(
                kind=kind,
                serial=match.group("serial"),
                vendor_id=int(match.group("vid"), 16),
                product_id=int(match.group("pid"), 16),
                label=label,
            )
        )
    return tuple(out)


def detect_probes(
    *,
    runner: process.CommandRunner | None = None,
    probe_rs_binary: str = "probe-rs",
) -> tuple[ProbeInfo, ...]:
    r = runner or process.runner
    # Prefer JSON; fall back to plain output.
    res = r.run([probe_rs_binary, "list", "--output=json"])
    if res.ok and res.stdout.strip():
        parsed = _parse_probe_rs_json(res.stdout)
        if parsed:
            return parsed
    res = r.run([probe_rs_binary, "list"])
    return _parse_probe_rs_plain(res.stdout)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select_probe(
    probes: tuple[ProbeInfo, ...],
    *,
    requested: str = "auto",
) -> ProbeInfo:
    """Return the probe matching ``requested`` (``auto`` means "the only one")."""
    if not probes:
        raise ProbeNotFoundError("No debug probe detected.  Plug one in or check `alloy doctor`.")
    if requested == "auto":
        if len(probes) == 1:
            return probes[0]
        listed = "\n".join(f"  • {p.short}" for p in probes)
        raise MultipleProbesError(
            f"{len(probes)} probes detected.  Pick one with --probe <kind>:\n{listed}"
        )
    matches = [p for p in probes if p.kind == requested.lower()]
    if not matches:
        raise ProbeNotFoundError(
            f"No probe of kind {requested!r} detected.  "
            f"Available: {', '.join({p.kind for p in probes}) or '(none)'}"
        )
    if len(matches) > 1:
        listed = "\n".join(f"  • {p.short}" for p in matches)
        raise MultipleProbesError(
            f"{len(matches)} {requested!r} probes detected.  "
            f"Pass --probe <kind>:<serial>:\n{listed}"
        )
    return matches[0]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _target_for(config: ProjectConfig) -> str | None:
    if config.chip is not None:
        return config.chip.device
    if config.board is not None:
        # Best-effort: probe-rs accepts the chip device id.  When we
        # only have a board, try to read the corresponding board.json
        # via core.boards (lazy import to keep the dependency surface
        # small).
        from alloy_cli.core import boards as _boards

        try:
            manifest = _boards.lookup(config.board.id)
            return manifest.device
        except BoardNotFoundError:
            return None
    return None


def run(
    *,
    elf: Path,
    config: ProjectConfig,
    probe_kind: str = "auto",
    target: str | None = None,
    runner: process.CommandRunner | None = None,
    on_line: Callable[[str], None] | None = None,
    require_toolchain: bool = True,
    project_root: Path | None = None,
) -> FlashResult:
    """Flash ``elf`` onto a connected probe.

    ``project_root`` defaults to the parent of ``elf`` and is the
    seam through which the event log is written.  Tests that build
    against a tmp dir already pass it implicitly.
    """
    if require_toolchain:
        status = _toolchain.detect_probe_rs()
        if not status.present:
            # OpenOCD fallback path is allowed if config opts in.
            if not config.flash.get("openocd_config") or not _toolchain.detect_openocd().present:
                raise ToolchainMissingError(
                    f"probe-rs is not installed: {status.install_hint}\n"
                    "Install probe-rs (preferred) or set [flash].openocd_config "
                    "and install openocd."
                )

    layout = AlloyDir(root=project_root or elf.parent.resolve())

    # Wave-2: prefer the project lockfile's pinned probe-rs over PATH.
    # When no lockfile pins probe-rs, fall back to the bare command
    # (PATH resolution; byte-identical to the pre-Wave-2 baseline).
    # Lockfile pin without matching store entry surfaces as a typed
    # FamilyToolchainInstallerVersionMismatchError up the stack.
    from alloy_cli.core import toolchain_manager as _tm

    pinned_probe_rs = _tm.resolve_for_lockfile(layout.root, "probe-rs")
    probe_rs_arg = str(pinned_probe_rs) if pinned_probe_rs is not None else "probe-rs"

    probes = detect_probes(runner=runner, probe_rs_binary=probe_rs_arg)
    probe = select_probe(probes, requested=probe_kind)

    chip = target or _target_for(config) or "auto"
    args = [probe_rs_arg, "run", "--chip", chip, str(elf)]
    if probe.serial:
        args.extend(["--probe", f"{probe.kind}:{probe.serial}"])


    record_event(
        layout, "flash_started", probe=probe.kind, target=chip, elf=str(elf)
    )

    r = runner or process.runner
    result = r.run(args, on_line=on_line)

    record_event(
        layout,
        "flash_finished",
        probe=probe.kind,
        target=chip,
        returncode=result.returncode,
    )
    return FlashResult(probe=probe, elf=elf, returncode=result.returncode, log=result.stdout)


__all__ = [
    "FlashResult",
    "MultipleProbesError",
    "ProbeInfo",
    "ProbeNotFoundError",
    "detect_probes",
    "run",
    "select_probe",
]
