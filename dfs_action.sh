#!/bin/sh
# hostapd_cli -a action; installed by the APK as /usr/libexec/aredn-dfs-action.sh.
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
exec logger -t hostapd-dfs -p "$dfs_priority" \
    "DFS_RELAY action_pid=$$ IFNAME=$dfs_iface $dfs_event"
