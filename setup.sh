#!/bin/sh

PKG_NAME="throttnux"

# CHECK_DEPS are for checking purpose because
# `iproute2` is not a binary which cannot be checked
CHECK_DEPS="tc dsniff arp-scan"
REQUIRED_DEPS="iproute2 dsniff arp-scan"
REQUIRED_PY_DEPS="psutil"
HAVE_MISSING_DEPS=0
HAVE_PY_MISSING_DEPS=0

PYTHON=""

log() {
    printf "\033[0m${PKG_NAME}::[INFO] %b\033[0m\n" "$@"
}

log_err() {
    printf "\033[1;31m${PKG_NAME}::[ERROR] %b\033[0m\n" "$@" >&2
}

log_prompt() {
    printf "\033[1;36m?\033[0m %b" "$@"
}

# ---------------- PRE-SETUP ----------------

# Check if user is not root
if [ "$(id -u)" -ne 0 ]; then
    log_err "Are you root? User '$(id -un)' ($(id -u)), please use sudo!"
    exit 1
fi

# -------------------------------------------

check_python() {
    if command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    elif command -v python >/dev/null 2>&1; then
        PYTHON=python
    else
        log_err "Python is not installed."
    fi
}

check_deps() {
    log "Checking required dependencies..."

    for dep in $CHECK_DEPS; do
        printf "  [ ] %s" "$dep"
        sleep 0.5 2>/dev/null

        path="$(command -v "$dep" 2>/dev/null)"
        if [ -n "$path" ]; then
            printf "\r  [x] %s -> %s\n" "$dep" "$path"
        else
            HAVE_MISSING_DEPS=1
        fi
    done
    unset path
}

check_py_deps() {
    if ! $PYTHON -c "import psutil" 2>/dev/null; then
        log_err "Missing Python package 'psutil'"
        HAVE_PY_MISSING_DEPS=1
    fi
}

install_pkg() {
    pkgs="$*"
    log "Installing required dependencies..."

    if command -v dnf >/dev/null 2>&1; then
        log "Using dnf package manager"
        dnf install -y $pkgs
    elif command -v pacman >/dev/null 2>&1; then
        log "Using pacman package manager"
        pacman -Sy --noconfirm $pkgs
    elif command -v apt-get >/dev/null 2>&1; then
        log "Using apt package manager"
        apt-get update
        apt-get install -y $pkgs
    elif command -v zypper >/dev/null 2>&1; then
        log "Using zypper package manager"
        zypper install -y $pkgs
    else
        log_err "Unsupported package manager"
        exit 1
    fi
}

run() {
    log "Initiating setup..."

    # ----- Python check

    check_python
    if [ -z "$PYTHON" ]; then
        echo
        log_prompt "Python v3 is required! Proceed to install? (Y/n) "
        read -r proceed

        if [ "$proceed" = 'y' ] || [ "$proceed" = 'Y' ] || [ "$proceed" = '' ]; then
            # The fallback is for Arch-based distros
            install_pkg python3 || install_pkg python
        else
            log_err "Python v3 is required to be installed!"
            exit 1
        fi
        unset proceed
    fi

    # ----- Dependencies

    check_deps
    if [ $HAVE_MISSING_DEPS -eq 1 ]; then
        echo
        log_prompt "Dependencies are missing. Proceed to install? (Y/n) "
        read -r proceed

        if [ "$proceed" = 'y' ] || [ "$proceed" = 'Y' ] || [ "$proceed" = '' ]; then
            echo
            install_pkg $REQUIRED_DEPS
        else
            log_err "Dependencies (${REQUIRED_DEPS}) are required!"
            exit 1
        fi
        unset proceed
    fi

    # ----- Python dependencies

    check_py_deps
    if [ $HAVE_PY_MISSING_DEPS -eq 1 ]; then
        echo
        log_prompt "Proceed to install 'psutil'? (Y/n) "
        read -r proceed

        if [ "$proceed" = 'y' ] || [ "$proceed" = 'Y' ] || [ "$proceed" = '' ]; then
            echo
            # The fallback is for Arch-based distros
            install_pkg python3-psutil || install_pkg python-psutil
        else
            log_err "Python dependency (${REQUIRED_PY_DEPS}) is required!"
            exit 1
        fi
        unset proceed
    fi

    echo
    echo "Everything is done! You can now run the program."
}

run