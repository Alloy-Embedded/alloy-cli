"""Regression guard: every ``AlloyCliError`` subclass declares a
unique ``error_type`` string.

LLM agents (via MCP) and CI scripts (e.g. ``check_error_cookbook.py``)
branch on ``error_type``.  A duplicate would silently widen one
class's contract over another's; a regression test catches it
before the merge.
"""

from __future__ import annotations

import inspect

from alloy_cli.core import errors as _errors


def _all_subclasses(cls: type) -> set[type]:
    """Recursive subclass walk."""
    out: set[type] = set()
    for sub in cls.__subclasses__():
        out.add(sub)
        out.update(_all_subclasses(sub))
    return out


def test_every_alloycli_error_type_string_is_unique() -> None:
    """Two different exception classes with the same ``error_type``
    would mean LLM agents cannot reliably branch on the field.
    """
    classes: list[type] = [_errors.AlloyCliError]
    classes.extend(sorted(_all_subclasses(_errors.AlloyCliError), key=lambda c: c.__name__))

    seen: dict[str, type] = {}
    duplicates: list[str] = []
    for cls in classes:
        et = getattr(cls, "error_type", None)
        assert isinstance(et, str) and et, (
            f"{cls.__name__} has no usable `error_type` class attribute"
        )
        if et in seen and seen[et] is not cls:
            duplicates.append(f"  • {et!r} on both {seen[et].__name__} and {cls.__name__}")
        else:
            seen[et] = cls

    assert not duplicates, "Duplicate error_type strings:\n" + "\n".join(duplicates)


def test_family_toolchain_error_subclasses_use_kebab_case() -> None:
    """The four ``family-toolchain-*`` sub-types follow the naming
    convention spec'd in `proposal.md`.
    """
    expected = {
        _errors.FamilyToolchainError: "family-toolchain-error",
        _errors.FamilyToolchainCycleError: "family-toolchain-cycle",
        _errors.FamilyToolchainUnknownParentError: "family-toolchain-unknown-parent",
        _errors.FamilyToolchainSchemaError: "family-toolchain-schema",
        _errors.FamilyToolchainNotFoundError: "family-toolchain-not-found",
    }
    for cls, expected_type in expected.items():
        assert cls.error_type == expected_type, (
            f"{cls.__name__}.error_type expected {expected_type!r}, got {cls.error_type!r}"
        )
        assert issubclass(cls, _errors.FamilyToolchainError), (
            f"{cls.__name__} should be a FamilyToolchainError subclass"
        )


def test_onboarding_cancelled_error_carries_stable_type() -> None:
    """Wave-3's wizard cancellation surfaces as ``onboarding-cancelled``.

    Distinct from the ``family-toolchain-*`` namespace because it's a
    user-flow event, not a toolchain content failure.
    """
    err = _errors.OnboardingCancelledError()
    assert err.error_type == "onboarding-cancelled"
    assert issubclass(_errors.OnboardingCancelledError, _errors.AlloyCliError)
    # NOT a FamilyToolchain* descendant — separate concept
    assert not issubclass(_errors.OnboardingCancelledError, _errors.FamilyToolchainError)
    assert not issubclass(
        _errors.OnboardingCancelledError,
        _errors.FamilyToolchainInstallerError,
    )


def test_onboarding_cancelled_error_attaches_partial_outcomes() -> None:
    """The exception carries what was installed before the cancel."""
    err = _errors.OnboardingCancelledError(
        "user cancelled",
        partial_outcomes=("outcome-a", "outcome-b"),
    )
    assert err.partial_outcomes == ("outcome-a", "outcome-b")
    assert "user cancelled" in str(err)


def test_family_toolchain_installer_error_subclasses_use_kebab_case() -> None:
    """The seven ``family-toolchain-installer-*`` sub-types follow the
    naming convention from Wave-2's proposal.
    """
    expected = {
        _errors.FamilyToolchainInstallerError: "family-toolchain-installer-error",
        _errors.FamilyToolchainInstallerChecksumError: "family-toolchain-installer-checksum",
        _errors.FamilyToolchainInstallerDownloadError: "family-toolchain-installer-download",
        _errors.FamilyToolchainInstallerExtractError: "family-toolchain-installer-extract",
        _errors.FamilyToolchainInstallerStoreCorruptError: "family-toolchain-installer-store-corrupt",
        _errors.FamilyToolchainInstallerVersionMismatchError: "family-toolchain-installer-version-mismatch",
        _errors.FamilyToolchainInstallerUnsupportedHostError: "family-toolchain-installer-unsupported-host",
        _errors.FamilyToolchainInstallerLockedError: "family-toolchain-installer-locked",
    }
    for cls, expected_type in expected.items():
        assert cls.error_type == expected_type, (
            f"{cls.__name__}.error_type expected {expected_type!r}, got {cls.error_type!r}"
        )
        assert issubclass(cls, _errors.FamilyToolchainInstallerError), (
            f"{cls.__name__} should be a FamilyToolchainInstallerError subclass"
        )
        # And the installer hierarchy lives directly under AlloyCliError —
        # NOT under FamilyToolchainError (that's the registry/loader family).
        assert not issubclass(cls, _errors.FamilyToolchainError), (
            f"{cls.__name__} should NOT extend FamilyToolchainError "
            "(installer is a sibling concept)"
        )


def test_every_exported_error_is_an_alloy_error() -> None:
    """``__all__`` should not leak unrelated exception types."""
    for name in _errors.__all__:
        obj = getattr(_errors, name)
        if not inspect.isclass(obj):
            continue
        assert issubclass(obj, _errors.AlloyCliError), (
            f"{name} listed in __all__ but is not an AlloyCliError subclass"
        )


def test_family_toolchain_probe_error_subclasses_use_kebab_case() -> None:
    """The five ``family-toolchain-probe-*`` sub-types follow the
    naming convention spec'd in Wave 4's proposal.
    """
    expected = {
        _errors.FamilyToolchainProbeError: "family-toolchain-probe-error",
        _errors.FamilyToolchainProbeNotFoundError: "family-toolchain-probe-not-found",
        _errors.FamilyToolchainProbeNotAttachedError: "family-toolchain-probe-not-attached",
        _errors.FamilyToolchainProbeMultipleAttachedError: (
            "family-toolchain-probe-multiple-attached"
        ),
        _errors.FamilyToolchainProbeUnauthorisedError: "family-toolchain-probe-unauthorised",
    }
    for cls, expected_type in expected.items():
        assert cls.error_type == expected_type, (
            f"{cls.__name__}.error_type expected {expected_type!r}, got {cls.error_type!r}"
        )
        assert issubclass(cls, _errors.FamilyToolchainProbeError), (
            f"{cls.__name__} should be a FamilyToolchainProbeError subclass"
        )


def test_family_toolchain_erase_error_subclasses_use_kebab_case() -> None:
    """The five ``family-toolchain-erase-*`` sub-types follow the
    naming convention spec'd in Wave 4's proposal.
    """
    expected = {
        _errors.FamilyToolchainEraseError: "family-toolchain-erase-error",
        _errors.FamilyToolchainEraseAbortedError: "family-toolchain-erase-aborted",
        _errors.FamilyToolchainEraseUnsupportedRegionError: (
            "family-toolchain-erase-unsupported-region"
        ),
        _errors.FamilyToolchainEraseConfirmationRequiredError: (
            "family-toolchain-erase-confirmation-required"
        ),
        _errors.FamilyToolchainEraseProbeFailedError: "family-toolchain-erase-probe-failed",
    }
    for cls, expected_type in expected.items():
        assert cls.error_type == expected_type, (
            f"{cls.__name__}.error_type expected {expected_type!r}, got {cls.error_type!r}"
        )
        assert issubclass(cls, _errors.FamilyToolchainEraseError), (
            f"{cls.__name__} should be a FamilyToolchainEraseError subclass"
        )
        # Erase errors live in their own family — not under
        # FamilyToolchainProbeError (they describe destination, not source).
        assert not issubclass(cls, _errors.FamilyToolchainProbeError), (
            f"{cls.__name__} should NOT extend FamilyToolchainProbeError"
        )


def test_probe_operation_cancelled_error_carries_session_summary() -> None:
    """The Wave-4 graceful-disconnect event carries duration + byte
    count + last-line so the CLI can summarise.  Distinct from
    ``OnboardingCancelledError`` because it's a different user-flow
    event — viewer disconnect vs. wizard abort."""
    err = _errors.ProbeOperationCancelledError(
        "user pressed ctrl+]",
        duration_ms=4720,
        bytes_captured=124,
        last_line="boot complete\n",
    )
    assert err.error_type == "probe-operation-cancelled"
    assert err.duration_ms == 4720
    assert err.bytes_captured == 124
    assert err.last_line == "boot complete\n"
    assert "user pressed ctrl+]" in str(err)
    # Distinct from OnboardingCancelledError — different user-flow events.
    assert not issubclass(_errors.ProbeOperationCancelledError, _errors.OnboardingCancelledError)
    assert not issubclass(_errors.OnboardingCancelledError, _errors.ProbeOperationCancelledError)


def test_probe_multiple_attached_error_carries_detected_tuple() -> None:
    """The error carries the (vid, pid, serial, kind) tuple per probe
    so the CLI / MCP envelope can render the list."""
    err = _errors.FamilyToolchainProbeMultipleAttachedError(
        detected=(
            ("0483", "374b", "0671FF1234567890", "stlink"),
            ("1366", "0101", "000123456789", "jlink"),
        ),
    )
    assert err.error_type == "family-toolchain-probe-multiple-attached"
    assert len(err.detected) == 2
    assert err.detected[0][0] == "0483"
    assert err.detected[1][3] == "jlink"


def test_probe_unauthorised_error_carries_vendor_tool_name() -> None:
    """Vendor-only probe surfaces the vendor tool name + install_doc URL
    so the user knows where to go."""
    err = _errors.FamilyToolchainProbeUnauthorisedError(
        vendor_tool="J-Link Commander",
        install_doc_url="https://www.segger.com/downloads/jlink/",
    )
    assert err.error_type == "family-toolchain-probe-unauthorised"
    assert err.vendor_tool == "J-Link Commander"
    assert err.install_doc_url is not None
    assert "segger" in err.install_doc_url


def test_erase_unsupported_region_error_carries_known_regions() -> None:
    """``--region not-a-region`` surfaces the regions the IR DOES
    declare so the user can pick a valid one."""
    err = _errors.FamilyToolchainEraseUnsupportedRegionError(
        known_regions=("bootloader", "appslot-a", "appslot-b"),
    )
    assert err.error_type == "family-toolchain-erase-unsupported-region"
    assert err.known_regions == ("bootloader", "appslot-a", "appslot-b")


def test_erase_probe_failed_error_carries_stderr_and_returncode() -> None:
    """A backend (probe-rs / openocd) failure during erase surfaces
    the raw stderr + non-zero returncode for debugging."""
    err = _errors.FamilyToolchainEraseProbeFailedError(
        stderr="error: probe-rs: Could not connect to target",
        returncode=2,
    )
    assert err.error_type == "family-toolchain-erase-probe-failed"
    assert "probe-rs" in err.stderr
    assert err.returncode == 2
