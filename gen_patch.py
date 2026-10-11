#!/usr/bin/env python3
from pathlib import Path

orig = Path(r"C:\Users\asher\terminalphone\terminalphone.sh")
text = orig.read_text(encoding="utf-8")

old = '''check_dep() {
    command -v "$1" &>/dev/null
}

install_deps() {'''

new = '''check_dep() {
    command -v "$1" &>/dev/null
}

required_deps_list() {
    if [ $IS_TERMUX -eq 1 ]; then
        echo tor opusenc opusdec sox socat openssl ffmpeg termux-microphone-record
    elif [ $IS_MACOS -eq 1 ]; then
        echo tor opusenc opusdec sox socat openssl rec play
    else
        echo tor opusenc opusdec sox socat openssl arecord aplay
    fi
}

check_required_deps() {
    local missing=()
    local dep
    for dep in $(required_deps_list); do
        if ! check_dep "$dep"; then
            missing+=("$dep")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        log_err "Missing required dependencies: ${missing[*]}"
        log_info "Install them with: bash $(basename "$0") install   (menu option 7)"
        exit 1
    fi
}

port_in_use() {
    local port="$1"
    if command -v ss &>/dev/null; then
        ss -ltn 2>/dev/null | grep -qE ":${port}[[:space:]]"
        return $?
    elif command -v lsof &>/dev/null; then
        lsof -nP -iTCP:"$port" -sTCP:LISTEN &>/dev/null
        return $?
    elif command -v netstat &>/dev/null; then
        netstat -ltn 2>/dev/null | grep -qE ":${port}[[:space:]]"
        return $?
    fi
    return 1
}

check_ports_before_tor() {
    local blocked=0
    if [ "$SINGLE_HOP" -ne 1 ] && port_in_use "$TOR_SOCKS_PORT"; then
        log_err "Port $TOR_SOCKS_PORT (SOCKS) is already in use"
        log_info "Stop the other Tor instance or change TOR_SOCKS_PORT in Settings -> Tor Settings"
        blocked=1
    fi
    if port_in_use "$LISTEN_PORT"; then
        log_err "Port $LISTEN_PORT (listen) is already in use"
        log_info "Stop the conflicting process or change LISTEN_PORT in Settings -> Tor Settings"
        blocked=1
    fi
    [ "$blocked" -eq 0 ]
}

tail_tor_log() {
    local tor_log="$TOR_DIR/tor.log"
    local lines="${1:-50}"
    if [ -f "$tor_log" ] && [ -s "$tor_log" ]; then
        echo -e "\\n${DIM}--- Last ${lines} lines of tor.log ---${NC}"
        tail -n "$lines" "$tor_log"
        echo -e "${DIM}--- end tor.log ---${NC}\\n"
    fi
}

diagnose_tor_failure() {
    local combined=""
    local f
    for f in "$TOR_DIR/tor.log" "$TOR_DIR/tor_stderr.log"; do
        [ -f "$f" ] && combined="${combined}$(cat "$f" 2>/dev/null)"
    done
    [ -z "$combined" ] && return 0

    if echo "$combined" | grep -qiE 'clock|time skew|system clock'; then
        log_warn "Possible clock skew — verify system time (e.g. timedatectl set-ntp true)"
    fi
    if echo "$combined" | grep -qiE 'Address already in use|Failed to bind'; then
        if echo "$combined" | grep -qE "9050|${TOR_SOCKS_PORT}"; then
            log_warn "SOCKS port $TOR_SOCKS_PORT is in use — change TOR_SOCKS_PORT or stop system Tor"
        fi
    fi
    if echo "$combined" | grep -qiE 'too permissive|Permission denied'; then
        log_warn "Hidden service directory permissions rejected by Tor"
        log_info "Use a native Linux filesystem (not /mnt/c on WSL). Clone to ~/terminalphone instead."
    fi
    if [ "$SNOWFLAKE_ENABLED" -eq 0 ] && echo "$combined" | grep -qiE 'connect.*fail|network is unreachable|No dir servers'; then
        log_warn "Network may block Tor — enable Snowflake bridge (SNOWFLAKE_ENABLED=1 in Settings -> Tor Settings)"
    fi
}

report_tor_failure() {
    local msg="${1:-Tor failed}"
    local tor_stderr="$TOR_DIR/tor_stderr.log"
    log_err "$msg"
    tail_tor_log 50
    if [ -f "$tor_stderr" ] && [ -s "$tor_stderr" ]; then
        echo -e "${DIM}--- Tor stderr ---${NC}"
        tail -n 50 "$tor_stderr"
        echo -e "${DIM}--- end stderr ---${NC}\\n"
    fi
    diagnose_tor_failure
}

check_data_filesystem() {
    local fstype mountpoint
    mountpoint=$(df "$DATA_DIR" 2>/dev/null | awk 'NR==2 {print $6}')
    fstype=$(findmnt -n -o FSTYPE "$DATA_DIR" 2>/dev/null || true)
    if [[ "$mountpoint" == /mnt/* ]] || [[ "$fstype" == "9p" ]] || [[ "$fstype" == "drvfs" ]]; then
        log_err "TerminalPhone data directory is on a Windows/WSL mount ($mountpoint)"
        log_info "Tor hidden services need a native Linux filesystem. Clone to ~/terminalphone and run from there."
        return 1
    fi
    return 0
}

install_deps() {'''

if old not in text:
    raise SystemExit("anchor1 not found")
text = text.replace(old, new, 1)

replacements = [
(
'''    setup_tor

    # Clear old log so we only see fresh output
    local tor_log="$TOR_DIR/tor.log"
    > "$tor_log"

    log_info "Starting Tor..."''',
'''    setup_tor

    check_data_filesystem || return 1
    check_ports_before_tor || return 1

    # Clear old log so we only see fresh output
    local tor_log="$TOR_DIR/tor.log"
    local tor_stderr="$TOR_DIR/tor_stderr.log"
    > "$tor_log"
    > "$tor_stderr"

    log_info "Starting Tor..."'''
),
('    tor -f "$TOR_CONF" &>/dev/null &', '    tor -f "$TOR_CONF" 2>>"$tor_stderr" &'),
(
'''        if ! kill -0 "$TOR_PID" 2>/dev/null; then
            echo ""
            log_err "Tor process died! Check $tor_log"
            [ -f "$tor_log" ] && tail -5 "$tor_log" 2>/dev/null
            return 1
        fi''',
'''        if ! kill -0 "$TOR_PID" 2>/dev/null; then
            echo ""
            local _tor_rc=0
            wait "$TOR_PID" 2>/dev/null || _tor_rc=$?
            report_tor_failure "Tor process died (command: tor -f \\"$TOR_CONF\\", exit: $_tor_rc)"
            return 1
        fi'''
),
(
'''    if [ $waited -ge $timeout ]; then
        echo ""
        log_err "Timed out waiting for Tor to bootstrap ($timeout seconds)"
        return 1
    fi''',
'''    if [ $waited -ge $timeout ]; then
        echo ""
        report_tor_failure "Timed out waiting for Tor to bootstrap (${timeout}s)"
        return 1
    fi'''
),
(
'''    else
        log_err "Tor bootstrapped but hidden service address not found"
        return 1
    fi
}''',
'''    else
        report_tor_failure "Tor bootstrapped but hidden service address not found at $ONION_FILE"
        return 1
    fi
}'''
),
(
'''trap cleanup EXIT INT TERM

# Create data directories''',
'''trap cleanup EXIT INT TERM

# Reject Windows CRLF line endings (common when cloning on Windows/WSL)
if grep -q $'\\r' "$0" 2>/dev/null; then
    echo -e "${RED}[FAIL]${NC} Windows CRLF line endings detected in $(basename "$0")"
    echo "Fix with: sed -i 's/\\r$//' $(basename "$0")"
    exit 1
fi

# Create data directories'''
),
(
'''# Handle command-line arguments
case "${1:-}" in
    install)
        install_deps
        ;;
    test)''',
'''# Handle command-line arguments
case "${1:-}" in
    install)
        install_deps
        ;;
    deps)
        missing=()
        for dep in $(required_deps_list); do
            if check_dep "$dep"; then
                log_ok "$dep -> $(command -v "$dep")"
            else
                log_err "$dep NOT FOUND"
                missing+=("$dep")
            fi
        done
        [ ${#missing[@]} -eq 0 ] || exit 1
        ;;
    test)'''
),
('''    test)
        test_audio
        ;;
    status)''',
'''    test)
        check_required_deps
        test_audio
        ;;
    status)'''
),
(
'''        echo "  install    Install dependencies"
        echo "  test       Run audio loopback test"''',
'''        echo "  install    Install dependencies"
        echo "  deps       Check required binaries in PATH"
        echo "  test       Run audio loopback test"'''
),
(
'''    *)
        main_menu
        ;;
esac''',
'''    *)
        check_required_deps
        main_menu
        ;;
esac'''
),
]

for old_s, new_s in replacements:
    if old_s not in text:
        raise SystemExit(f"anchor not found: {old_s[:60]!r}")
    text = text.replace(old_s, new_s, 1)

patched = orig.with_name("terminalphone.sh.patched")
patched.write_text(text, encoding="utf-8", newline="\n")
print(f"Wrote {patched}")
