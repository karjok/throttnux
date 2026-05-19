import re
import sys
import time
import logging

from .cmds import runWithoutCheck as run

log = logging.getLogger("throttnux")


def format_bytes(b):
    """Convert bytes to human-readable string."""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 ** 3:
        return f"{b / 1024 ** 2:.1f} MB"
    return f"{b / 1024 ** 3:.2f} GB"


def get_tc_stats(interface):
    """
    Read tc class 1:10 stats.
    Returns (bytes_sent, pkts_sent, pkts_overlimit) or None if unavailable.
    """
    result = run(f"tc -s class show dev {interface}")
    lines  = result.stdout.splitlines()

    for i, line in enumerate(lines):
        if "1:10" in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.search(r"Sent (\d+) bytes (\d+) pkt.*overlimits (\d+)", lines[j])
                if m:
                    return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def verify_spoofing(interface, stop_event):
    """
    Auto-verify whether spoofing successfully captured target traffic.
    If no traffic is detected after 5 seconds, stop the program.
    """
    log.info("Verifying spoofing status (waiting 5 seconds)...")
    time.sleep(5)

    if stop_event.is_set():
        return

    stats = get_tc_stats(interface)
    if stats:
        _, pkts, _ = stats
        if pkts > 0:
            log.info(f"Spoofing SUCCESSFUL — {pkts} packets captured from target")
        else:
            log.warning("Target device does not appear to be using the network.")
            log.warning("Stopping Throttnux.")
            stop_event.set()


def live_monitor(interface, target_ip, limit_mbps, stop_event):
    """
    Realtime bandwidth monitor — updates in-place every second.
    Shows current Mbps, status indicator, total data throttled, and uptime.

    Status indicator:
      ● — throttling active (overlimit packets detected)
      ○ — idle or spoofing not yet effective

    If target goes offline, program keeps running and waits for reconnection.
    If target comes back online, throttling resumes automatically.
    """
    time.sleep(6)

    start_time    = time.time()
    prev_bytes    = 0
    prev_time     = time.time()
    idle_seconds  = 0
    IDLE_TIMEOUT  = 10
    target_online = True

    print()

    while not stop_event.is_set():
        stats = get_tc_stats(interface)

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

            if delta_bytes == 0 and uptime > 15:
                idle_seconds += 1
                if idle_seconds >= IDLE_TIMEOUT and target_online:
                    sys.stdout.write("\r" + " " * 100 + "\r")
                    sys.stdout.flush()
                    log.warning("Target device appears to have gone offline. Waiting for reconnection...")
                    target_online = False
            else:
                if not target_online:
                    log.info("Target device is back online. Throttling resumed.")
                    target_online = True
                idle_seconds = 0

            if target_online:
                line = (
                    f"\r[LIVE {status}] {target_ip} → "
                    f"{mbps:.2f} Mbps / {limit_mbps} Mbps limit | "
                    f"{total_str} throttled | "
                    f"Uptime: {uptime_str}   "
                )
                sys.stdout.write(line)
                sys.stdout.flush()

            prev_bytes = total_bytes
            prev_time  = now

        time.sleep(1)

    sys.stdout.write("\r" + " " * 100 + "\r")
    sys.stdout.flush()