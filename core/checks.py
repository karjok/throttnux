import os
import sys
import subprocess
import logging

log = logging.getLogger("throttnux")


def check_os():
    if sys.platform != "linux":
        log.error("Throttnux only supports Linux.")
        log.error("Windows and macOS are not supported.")
        sys.exit(1)


def check_root():
    if os.geteuid() != 0:
        log.error("This script must be run as root.")
        log.error("Try: sudo python3 main.py")
        sys.exit(1)


def check_dependencies():
    missing = []
    for tool in ["arpspoof", "tc", "arp-scan"]:
        result = subprocess.run(
            f"which {tool}",
            shell=True,
            capture_output=True
        )
        if result.returncode != 0:
            missing.append(tool)

    if missing:
        log.error(f"Missing required tools: {', '.join(missing)}")
        log.error("Fedora/RHEL  : sudo dnf install dsniff arp-scan")
        log.error("Debian/Ubuntu: sudo apt install dsniff arp-scan")
        log.error("Arch Linux   : sudo pacman -S dsniff arp-scan")
        sys.exit(1)