"""Agent packaging — platform detection, systemd/service integration, installer generation."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.agent.packaging")


class PlatformFamily(str, Enum):
    LINUX_DEB = "linux_deb"
    LINUX_RPM = "linux_rpm"
    LINUX_GENERIC = "linux_generic"
    WINDOWS = "windows"
    MACOS = "macos"
    EMBEDDED_LINUX = "embedded_linux"
    UNKNOWN = "unknown"


@dataclass
class PlatformInfo:
    """Detected platform information."""
    family: PlatformFamily
    os_name: str
    os_version: str
    arch: str
    hostname: str = ""
    python_version: str = ""
    has_systemd: bool = False
    has_docker: bool = False
    has_tpm: bool = False
    total_disk_mb: int = 0
    free_disk_mb: int = 0
    total_memory_mb: int = 0
    cpu_count: int = 0
    selinux_enabled: bool = False
    apparmor_enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "family": self.family.value, "os_name": self.os_name, "os_version": self.os_version,
            "arch": self.arch, "hostname": self.hostname, "python_version": self.python_version,
            "has_systemd": self.has_systemd, "has_docker": self.has_docker, "has_tpm": self.has_tpm,
            "total_disk_mb": self.total_disk_mb, "free_disk_mb": self.free_disk_mb,
            "total_memory_mb": self.total_memory_mb, "cpu_count": self.cpu_count,
            "selinux_enabled": self.selinux_enabled, "apparmor_enabled": self.apparmor_enabled,
        }


def detect_platform() -> PlatformInfo:
    """Detect current platform details."""
    import sys
    system = platform.system().lower()
    arch = platform.machine()
    os_version = platform.version()
    hostname = platform.node()
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    family = PlatformFamily.UNKNOWN
    has_systemd = False
    has_docker = False
    has_tpm = False
    selinux = False
    apparmor = False
    total_disk = 0
    free_disk = 0
    total_mem = 0
    cpu_count = os.cpu_count() or 0

    if system == "linux":
        if Path("/usr/bin/dpkg").exists() or Path("/usr/bin/apt").exists():
            family = PlatformFamily.LINUX_DEB
        elif Path("/usr/bin/rpm").exists() or Path("/usr/bin/yum").exists() or Path("/usr/bin/dnf").exists():
            family = PlatformFamily.LINUX_RPM
        else:
            family = PlatformFamily.LINUX_GENERIC
        has_systemd = Path("/run/systemd/system").is_dir() or Path("/usr/bin/systemctl").exists()
        has_docker = shutil.which("docker") is not None
        has_tpm = Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists()
        selinux = Path("/etc/selinux/config").exists()
        apparmor = Path("/sys/module/apparmor").exists()
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_mem = int(line.split()[1]) // 1024
                        break
        except (OSError, ValueError):
            pass
    elif system == "windows":
        family = PlatformFamily.WINDOWS
    elif system == "darwin":
        family = PlatformFamily.MACOS

    try:
        usage = shutil.disk_usage("/")
        total_disk = usage.total // (1024 * 1024)
        free_disk = usage.free // (1024 * 1024)
    except OSError:
        pass

    os_name = platform.system()
    if system == "linux":
        try:
            import distro
            os_name = distro.name(pretty=True)
            os_version = distro.version()
        except ImportError:
            try:
                result = subprocess.run(["lsb_release", "-ds"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    os_name = result.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

    return PlatformInfo(
        family=family, os_name=os_name, os_version=os_version, arch=arch,
        hostname=hostname, python_version=python_ver, has_systemd=has_systemd,
        has_docker=has_docker, has_tpm=has_tpm, total_disk_mb=total_disk,
        free_disk_mb=free_disk, total_memory_mb=total_mem, cpu_count=cpu_count,
        selinux_enabled=selinux, apparmor_enabled=apparmor,
    )


def generate_systemd_unit(service_name: str = "waveos-agent", exec_start: str = "/usr/local/bin/waveos agent-v2 status", user: str = "waveos", working_dir: str = "/opt/waveos") -> str:
    """Generate a systemd unit file for the WaveOS agent."""
    return f"""[Unit]
Description=WaveOS Agent ({service_name})
After=network-online.target
Wants=network-online.target
Documentation=https://waveos.io/docs/agent

[Service]
Type=simple
User={user}
Group={user}
WorkingDirectory={working_dir}
ExecStart={exec_start}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier={service_name}
Environment=WAVEOS_LICENSE_KEY=
ProtectSystem=strict
ReadWritePaths=/opt/waveos /var/log/waveos
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""


def generate_install_script(install_prefix: str = "/opt/waveos", service_name: str = "waveos-agent") -> str:
    """Generate a portable install script for the WaveOS agent."""
    return f"""#!/bin/bash
set -euo pipefail

PREFIX="{install_prefix}"
SERVICE="{service_name}"

echo "Installing WaveOS Agent to $PREFIX"
mkdir -p "$PREFIX/bin" "$PREFIX/apps" "$PREFIX/agent" "$PREFIX/registry"
mkdir -p /var/log/waveos

if command -v pip3 &>/dev/null; then
    pip3 install --prefix "$PREFIX" waveos
elif command -v pip &>/dev/null; then
    pip install --prefix "$PREFIX" waveos
else
    echo "ERROR: pip not found. Install Python 3.11+ first."
    exit 1
fi

if [ -d /run/systemd/system ]; then
    echo "Installing systemd unit"
    cat > /etc/systemd/system/$SERVICE.service << 'UNIT'
{generate_systemd_unit(service_name)}
UNIT
    systemctl daemon-reload
    systemctl enable $SERVICE
    echo "Enabled $SERVICE.service"
fi

echo "Install complete. Start with: systemctl start $SERVICE"
"""


def get_device_identity_from_tpm() -> Dict[str, Any]:
    """Attempt to read device identity from TPM (if available)."""
    identity: Dict[str, Any] = {"source": "none", "device_id": "", "tpm_available": False}
    if Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists():
        identity["tpm_available"] = True
        try:
            result = subprocess.run(["tpm2_getcap", "properties-fixed"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "TPM2_PT_VENDOR_STRING" in line:
                        identity["tpm_vendor"] = line.split(":")[-1].strip()
                identity["source"] = "tpm"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        identity["device_id"] = machine_id_path.read_text().strip()
        if not identity["source"] or identity["source"] == "none":
            identity["source"] = "machine-id"
    if not identity["device_id"]:
        identity["device_id"] = platform.node()
        identity["source"] = "hostname"
    return identity


def generate_hardening_profile(platform_info: PlatformInfo) -> Dict[str, Any]:
    """Generate security hardening recommendations for the platform."""
    recommendations: List[Dict[str, str]] = []
    if platform_info.family in (PlatformFamily.LINUX_DEB, PlatformFamily.LINUX_RPM, PlatformFamily.LINUX_GENERIC):
        if not platform_info.selinux_enabled and not platform_info.apparmor_enabled:
            recommendations.append({"area": "MAC", "recommendation": "Enable SELinux or AppArmor for mandatory access control"})
        if platform_info.has_systemd:
            recommendations.append({"area": "service", "recommendation": "Use systemd unit with ProtectSystem=strict, NoNewPrivileges=true"})
        recommendations.append({"area": "user", "recommendation": "Run agent as dedicated 'waveos' user, not root"})
        recommendations.append({"area": "filesystem", "recommendation": "Mount /opt/waveos/apps as noexec if possible"})
    if platform_info.has_tpm:
        recommendations.append({"area": "identity", "recommendation": "Use TPM for device identity attestation"})
    return {"platform": platform_info.family.value, "recommendations": recommendations}
