#!/usr/bin/env python3

import sys
import signal
import atexit
import logging
import threading

from core import (
    check_os,
    check_root,
    check_dependencies,
    pick_interface,
    pick_router,
    scan_devices,
    pick_target,
    pick_limit,
    enable_ip_forward,
    disable_ip_forward,
    setup_traffic_shaping,
    cleanup_traffic_shaping,
    arp_spoof_loop,
    verify_spoofing,
    live_monitor,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("throttnux")

stop_event = threading.Event()


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


def banner():
    print("""
Welcome to Throttnux
Per-device bandwidth limiter via ARP spoofing
""")


def signal_handler(sig, frame):
    print()
    log.info("Interrupt received. Cleaning up...")
    stop_event.set()


def main():
    check_os()
    check_root()
    check_dependencies()

    banner()

    # 1. Auto-detect interface and router interactively
    interface = pick_interface(prompt)
    router_ip = pick_router(interface, prompt)

    # 2. Scan and pick target device
    devices    = scan_devices(interface, router_ip)
    target     = pick_target(devices, prompt)
    target_ip  = target["ip"]
    target_mac = target["mac"]

    # 3. Pick bandwidth limit
    limit_mbps = pick_limit(prompt)

    # 4. Confirm
    print("\n" + "=" * 58)
    print(f"  Target    : {target_ip} ({target_mac})")
    print(f"  Vendor    : {target['vendor']}")
    print(f"  Limit     : {limit_mbps} Mbps")
    print(f"  Interface : {interface}")
    print(f"  Router    : {router_ip}")
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
    atexit.register(lambda: (
        cleanup_traffic_shaping(interface),
        disable_ip_forward()
    ))

    # 6. Setup
    enable_ip_forward()
    setup_traffic_shaping(interface, target_ip, limit_mbps)

    # 7. ARP spoofing in background thread
    spoof_thread = threading.Thread(
        target=arp_spoof_loop,
        args=(interface, target_ip, router_ip, stop_event),
        daemon=True
    )
    spoof_thread.start()

    # 8. Verify spoofing in background thread
    verify_thread = threading.Thread(
        target=verify_spoofing,
        args=(interface, stop_event),
        daemon=True
    )
    verify_thread.start()

    # 9. Realtime monitor in background thread
    monitor_thread = threading.Thread(
        target=live_monitor,
        args=(interface, target_ip, limit_mbps, stop_event),
        daemon=True
    )
    monitor_thread.start()

    log.info("Running. Press Ctrl+C to stop and restore target connection.")

    # 10. Wait for stop signal
    stop_event.wait()

    # 11. Cleanup
    spoof_thread.join(timeout=5)
    cleanup_traffic_shaping(interface)
    disable_ip_forward()

    log.info("Done. Target connection restored.")


if __name__ == "__main__":
    main()