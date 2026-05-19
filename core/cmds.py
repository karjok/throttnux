import subprocess
import logging

log = logging.getLogger("throttnux")

def run(cmd: str, check: bool = True):
    """Run shell command with check."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        log.error(f"Command failed: {cmd}\n{result.stderr.strip()}")
    return result

def runWithoutCheck(cmd: str):
    """Run shell command without check."""
    return run(cmd, False)
