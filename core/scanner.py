import re
import sys
import subprocess
import logging

log = logging.getLogger("throttnux")


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def scan_devices(interface, router_ip):
    """Scan all active devices on the local network using arp-scan."""
    log.info("Scanning network for active devices...")
    result = run(f"arp-scan --localnet -I {interface}")

    devices = []
    for line in result.stdout.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+([\w:]+)\s*(.*)", line)
        if match:
            ip, mac, vendor = match.groups()
            if ip == router_ip:
                continue
            devices.append({
                "ip":     ip,
                "mac":    mac.lower(),
                "vendor": vendor.strip() if vendor.strip() else "Unknown"
            })

    return devices


def pick_target(devices, prompt_fn):
    """Display device list and prompt user to pick a target."""
    if not devices:
        log.error("No devices found on the network.")
        sys.exit(1)

    print("\n" + "=" * 58)
    print("  Devices detected on the network:")
    print("=" * 58)
    print(f"  {'No':<5} {'IP':<16} {'MAC':<20} {'Vendor'}")
    print("  " + "-" * 53)

    for i, dev in enumerate(devices, 1):
        print(f"  {i:<5} {dev['ip']:<16} {dev['mac']:<20} {dev['vendor'][:22]}")

    print("=" * 58)

    idx = prompt_fn("\n  Select device number to throttle: ", valid_range=len(devices))
    return devices[idx]


def pick_limit(prompt_fn):
    """Prompt user to select a bandwidth limit."""
    print("\n  Select bandwidth limit:")
    print("  [1] 1 Mbps  — heavy buffering, no HD YouTube")
    print("  [2] 2 Mbps  — stuck at 480p")
    print("  [3] 3 Mbps  — occasional buffering at 720p")
    print("  [4] Custom")

    presets = {"1": 1.0, "2": 2.0, "3": 3.0}

    while True:
        try:
            choice = input("\n  Choice (1-4): ").strip()
            if choice in presets:
                return presets[choice]
            elif choice == "4":
                val = float(input("  Enter limit in Mbps: ").strip())
                if val <= 0:
                    print("  [!] Limit must be greater than 0.")
                    continue
                return val
            else:
                print("  [!] Please choose 1-4.")
        except ValueError:
            print("  [!] Invalid input.")
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            sys.exit(0)