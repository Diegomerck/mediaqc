"""Packaging smoke tests without introducing an engine entry point."""

import subprocess
import sys
from importlib.metadata import version


def test_package_is_installed() -> None:
    assert version("mediaqc-engine") == "0.1.0"


def test_import_is_silent() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import mediaqc_engine"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
