"""Tests for ``alloy_cli.core.memory``: ELF size parsing."""

from __future__ import annotations

from pathlib import Path

from alloy_cli.core.memory import MemoryReport, format_summary, parse_elf
from alloy_cli.core.process import FakeRunner


def test_format_summary_renders_kib_and_bytes() -> None:
    report = MemoryReport(text_bytes=10240, data_bytes=512, bss_bytes=4096)
    text = format_summary(report)
    assert "flash=" in text
    assert "ram=" in text
    assert str(10240 + 512) in text  # flash bytes
    assert str(512 + 4096) in text  # ram bytes


def test_memory_report_flash_and_ram_totals() -> None:
    report = MemoryReport(text_bytes=1000, data_bytes=200, bss_bytes=500)
    assert report.flash_bytes == 1200
    assert report.ram_bytes == 700


def test_parse_elf_returns_none_when_size_binary_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    elf = tmp_path / "f.elf"
    elf.write_bytes(b"\x7fELF")
    assert parse_elf(elf) is None


def test_parse_elf_parses_berkeley_output(monkeypatch, tmp_path) -> None:
    elf = tmp_path / "f.elf"
    elf.write_bytes(b"\x7fELF")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "size" else None)
    fake = FakeRunner()
    fake.expect(
        ["size", "--format=berkeley"],
        returncode=0,
        stdout=(
            "   text	   data	    bss	    dec	    hex	filename\n"
            f"  10240	    512	   4096	  14848	   3a00	{elf}\n"
        ),
    )
    report = parse_elf(elf, runner=fake)
    assert report is not None
    assert report.text_bytes == 10240
    assert report.data_bytes == 512
    assert report.bss_bytes == 4096


def test_parse_elf_returns_none_on_size_failure(monkeypatch, tmp_path) -> None:
    elf = tmp_path / "f.elf"
    elf.write_bytes(b"\x7fELF")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "size" else None)
    fake = FakeRunner()
    fake.expect(["size"], returncode=1, stdout="")
    assert parse_elf(elf, runner=fake) is None


def test_parse_elf_prefers_arm_none_eabi_size_when_available(monkeypatch, tmp_path) -> None:
    elf = tmp_path / "f.elf"
    elf.write_bytes(b"\x7fELF")
    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/opt/{name}" if name == "arm-none-eabi-size" else None,
    )
    fake = FakeRunner()
    fake.expect(
        ["arm-none-eabi-size", "--format=berkeley", str(elf)],
        returncode=0,
        stdout=(
            "   text	   data	    bss	    dec	    hex	filename\n"
            "    100	     20	     30	    150	     96	" + str(elf) + "\n"
        ),
    )
    report = parse_elf(elf, runner=fake)
    assert report is not None
    assert report.text_bytes == 100


def test_parse_elf_path_arg_does_not_have_to_exist(monkeypatch, tmp_path) -> None:
    """``parse_elf`` shells out — it doesn't probe the filesystem itself."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name if name == "size" else None)
    fake = FakeRunner()
    fake.expect(
        ["size"],
        returncode=0,
        stdout="   text\tdata\tbss\tdec\thex\tfilename\n   1\t2\t3\t6\t6\tnope\n",
    )
    report = parse_elf(Path("/does-not-exist.elf"), runner=fake)
    assert report is not None
    assert report.text_bytes == 1
