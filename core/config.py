import json
import os
import logging

log = logging.getLogger("throttnux")

CONFIG_DIR  = os.path.expanduser("~/.config/throttnux")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def save_config(interface, router_ip, target_ip, target_mac, target_vendor, limit_mbps):
    """Save last session config to ~/.config/throttnux/config.json."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config = {
        "interface":     interface,
        "router_ip":     router_ip,
        "target_ip":     target_ip,
        "target_mac":    target_mac,
        "target_vendor": target_vendor,
        "limit_mbps":    limit_mbps,
    }
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        log.info(f"Config saved to {CONFIG_FILE}")
    except Exception as e:
        log.warning(f"Failed to save config: {e}")


def load_config():
    """Load config from ~/.config/throttnux/config.json if it exists."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load config: {e}")
        return None


def prompt_use_saved_config(config):
    """Ask user if they want to use the saved config."""
    vendor = config['target_vendor']
    if "locally administered" in vendor.lower() or not vendor:
        vendor = "Unknown"

    print("\n" + "=" * 58)
    print("  Saved config detected:")
    print("  " + "-" * 54)
    print(f"  Target    : {config['target_ip']} ({config['target_mac']})")
    print(f"  Vendor    : {vendor}")
    print(f"  Limit     : {config['limit_mbps']} Mbps")
    print(f"  Interface : {config['interface']}")
    print(f"  Router    : {config['router_ip']}")
    print("=" * 58)

    while True:
        try:
            choice = input("\n  Use saved config? (y/n): ").strip().lower()
            if choice in ("y", ""):
                if choice == "":
                    print("\033[A  Use saved config? (y/n): y")
                return True
            elif choice == "n":
                return False
            else:
                print("  [!] Please enter y or n.")
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            import sys
            sys.exit(0)