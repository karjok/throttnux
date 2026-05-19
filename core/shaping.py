import logging

from .cmds import run

log = logging.getLogger("throttnux")


def enable_ip_forward():
    log.info("Enabling IP forwarding...")
    run("echo 1 > /proc/sys/net/ipv4/ip_forward")


def disable_ip_forward():
    log.info("Disabling IP forwarding...")
    run("echo 0 > /proc/sys/net/ipv4/ip_forward")


def setup_traffic_shaping(interface, target_ip, limit_mbps):
    log.info(f"Setting up traffic shaping → {limit_mbps} Mbps limit for {target_ip}")
    limit_kbit = int(limit_mbps * 1000)

    run(f"tc qdisc del dev {interface} root", check=False)

    cmds = [
        f"tc qdisc add dev {interface} root handle 1: htb default 99",
        f"tc class add dev {interface} parent 1: classid 1:99 htb rate 1000mbit",
        f"tc class add dev {interface} parent 1: classid 1:10 htb rate {limit_kbit}kbit burst 10k",
        f"tc filter add dev {interface} parent 1: protocol ip prio 1 u32 match ip dst {target_ip}/32 flowid 1:10",
        f"tc filter add dev {interface} parent 1: protocol ip prio 2 u32 match ip src {target_ip}/32 flowid 1:10",
    ]

    for cmd in cmds:
        run(cmd)

    log.info(f"Traffic shaping active → target limited to {limit_mbps} Mbps")


def cleanup_traffic_shaping(interface):
    log.info("Removing traffic shaping rules...")
    run(f"tc qdisc del dev {interface} root", check=False)