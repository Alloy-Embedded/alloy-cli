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
            duplicates.append(
                f"  • {et!r} on both {seen[et].__name__} and {cls.__name__}"
            )
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
            f"{cls.__name__}.error_type expected {expected_type!r}, "
            f"got {cls.error_type!r}"
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
