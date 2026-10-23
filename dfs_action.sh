#!/bin/sh
# Optional hostapd_cli -a action. Stage in /tmp only when deployment is intended.
# Upstream passes: $1 = interface, $2 = event token, $3... = event fields.
# This relays reports to syslog; it never changes radio/configuration state.

if [ "$#" -lt 2 ]; then
    printf '%s\n' 'dfs_action: expected interface, event and optional fields' >&2
    exit 2
fi

dfs_iface=$1
shift
case "$dfs_iface" in
    ''|*[!A-Za-z0-9_.-]*)
        printf '%s\n' 'dfs_action: invalid interface' >&2
        exit 2
        ;;
esac

# Exact tokens only; a test/suffix or unrelated event is not a radar report.
case "$1" in
    DFS-RADAR-DETECTED) dfs_priority=daemon.notice ;;
    DFS-CAC-START|DFS-CAC-COMPLETED|DFS-NOP-FINISHED|DFS-PRE-CAC-EXPIRED|\
    DFS-NEW-CHANNEL|AP-CSA-FINISHED|CTRL-EVENT-CHANNEL-SWITCH)
        dfs_priority=daemon.info
        ;;
    *) exit 0 ;;
esac

# Rejoin EVERY argument after the interface, not just $2 of the original call.
# Quoted expansion is data, not shell code. Do not use eval.
IFS=' '
dfs_event=$*
dfs_newline='
'
dfs_cr=$(printf '\r')
case "$dfs_event" in
    *"$dfs_newline"*|*"$dfs_cr"*)
        printf '%s\n' 'dfs_action: multiline event rejected' >&2
        exit 2
        ;;
esac

# PID distinguishes same-second action invocations; preserve boot/log timestamps
# too. Native log + relay copies are NOT deduplicated as physical incidents.
dfs_result=0
logger -t hostapd-dfs -p "$dfs_priority" \
    "DFS_RELAY action_pid=$$ IFNAME=$dfs_iface $dfs_event"
dfs_result=$?

# Optional native banner: explicitly enable by setting an absolute helper path.
# Never invoke for CAC/NOP/channel changes. Frequency is the event's own freq,
# not cf1, a status-page value, or the newly selected channel.
if [ "$1" = DFS-RADAR-DETECTED ] && [ -n "${DFS_BANNER_HELPER:-}" ]; then
    dfs_freq=unknown
    dfs_freq_count=0
    for dfs_arg in "$@"; do
        case "$dfs_arg" in
            freq=*) dfs_freq=${dfs_arg#freq=}; dfs_freq_count=$((dfs_freq_count + 1)) ;;
        esac
    done
    if [ "$dfs_freq_count" -ne 1 ]; then
        dfs_freq=unknown
    fi
    case "$dfs_freq" in ''|*[!0-9]*|0*) dfs_freq=unknown ;; esac
    case "$DFS_BANNER_HELPER" in
        /*) DFS_BANNER_NOISE_IFACE="$dfs_iface" "$DFS_BANNER_HELPER" report "${DFS_NODE_NAME:-$(uname -n)}" "$dfs_iface" "$dfs_freq" hostapd_cli || dfs_result=$? ;;
        *) printf '%s\n' 'dfs_action: banner helper must be an absolute path' >&2; dfs_result=2 ;;
    esac
fi
exit "$dfs_result"
