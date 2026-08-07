"""Best-effort installation of the optional OfficeCLI dependency."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

OFFICECLI_WINDOWS_INSTALL = "irm https://d.officecli.ai/install.ps1 | iex"
OFFICECLI_POSIX_INSTALL = "curl -fsSL https://d.officecli.ai/install.sh | bash"


@dataclass(frozen=True)
class OfficeCliInstallResult:
    installed: bool
    attempted: bool
    warning: str = ""


def officecli_installed() -> bool:
    """Return whether the OfficeCLI executable is currently discoverable."""
    return shutil.which("officecli") is not None


def _installer_command(platform_name: str) -> list[str]:
    if platform_name == "win32":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            OFFICECLI_WINDOWS_INSTALL,
        ]
    return ["bash", "-lc", OFFICECLI_POSIX_INSTALL]


def install_officecli(*, platform_name: str | None = None) -> OfficeCliInstallResult:
    """Install OfficeCLI if absent, without making it a hard dependency."""
    platform_name = platform_name or sys.platform
    if officecli_installed():
        return OfficeCliInstallResult(installed=True, attempted=False)

    if platform_name not in {"win32", "darwin", "linux"}:
        return OfficeCliInstallResult(
            installed=False,
            attempted=False,
            warning=f"OfficeCLI installation is unsupported on platform {platform_name!r}",
        )

    try:
        completed = subprocess.run(
            _installer_command(platform_name),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        return OfficeCliInstallResult(
            installed=False,
            attempted=True,
            warning="OfficeCLI installation timed out after 10 minutes",
        )
    except Exception as exc:
        return OfficeCliInstallResult(
            installed=False,
            attempted=True,
            warning=f"OfficeCLI installer could not run: {exc}",
        )

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {details[-300:]}" if details else ""
        return OfficeCliInstallResult(
            installed=False,
            attempted=True,
            warning=f"OfficeCLI installer exited with code {completed.returncode}{suffix}",
        )

    if officecli_installed():
        return OfficeCliInstallResult(installed=True, attempted=True)

    return OfficeCliInstallResult(
        installed=False,
        attempted=True,
        warning="OfficeCLI installer completed, but the command is still not on PATH",
    )
