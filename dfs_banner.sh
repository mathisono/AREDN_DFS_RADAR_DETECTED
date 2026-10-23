#!/bin/sh
# Native AREDN announcement sink. Only a task-owned /tmp message is replaced.
# report NODE IFACE FREQ SOURCE | demo NODE | clear
# DFS_BANNER_NOISE_IFACE opts into a passive local-radio noise snapshot.
set -eu

dfs_messages=${DFS_BANNER_DIR:-/tmp/other_messages}
dfs_messages=${dfs_messages%/}
case "$dfs_messages" in
    /*) ;;
    *) printf '%s\n' 'dfs_banner: an absolute message directory is required' >&2; exit 2 ;;
esac
dfs_output=$dfs_messages/aredn-dfs-detection-test
dfs_mode=${1:-}

if [ "$dfs_mode" = clear ] && [ "$#" -eq 1 ]; then
    # Do not touch native downloaded alerts or another add-on's announcement.
    [ ! -L "$dfs_messages" ] || exit 2
    rm -f -- "$dfs_output"
    exit 0
fi

case "$dfs_mode:$#" in
    report:5)
        dfs_node=$2; dfs_iface=$3; dfs_freq=$4; dfs_source=$5
        dfs_heading='Radar reported'
        dfs_note='Last report, not current DFS/NOP state. Detection only; no recovery action.'
        ;;
    demo:2)
        dfs_node=$2; dfs_iface=example; dfs_freq=5660; dfs_source=display-fixture
        dfs_heading='SIMULATED - display check only'
        dfs_note='Not a real radar detection. No radio or recovery action.'
        ;;
    *) printf '%s\n' 'usage: dfs_banner.sh report NODE IFACE FREQ SOURCE | demo NODE | clear' >&2; exit 2 ;;
esac

dfs_when=${DFS_BANNER_OBSERVED_AT:-$(date -u '+%Y-%m-%dT%H:%M:%SZ')}
dfs_newline='
'
dfs_cr=$(printf '\r')
for dfs_value in "$dfs_node" "$dfs_iface" "$dfs_source" "$dfs_when"; do
    [ "${#dfs_value}" -le 160 ] || { printf '%s\n' 'dfs_banner: text too long' >&2; exit 2; }
    case "$dfs_value" in
        *"$dfs_newline"*|*"$dfs_cr"*) printf '%s\n' 'dfs_banner: multiline text rejected' >&2; exit 2 ;;
    esac
done

dfs_channel=unknown
case "$dfs_freq" in
    unknown) dfs_frequency='unknown frequency' ;;
    ''|*[!0-9]*|0*) printf '%s\n' 'dfs_banner: invalid frequency' >&2; exit 2 ;;
    *)
        [ "${#dfs_freq}" -le 5 ] || exit 2
        if [ "$dfs_freq" -gt 5000 ] && [ "$dfs_freq" -lt 5925 ] && [ "$((dfs_freq % 5))" -eq 0 ]; then
            dfs_channel=$(((dfs_freq - 5000) / 5))
        fi
        dfs_frequency="$dfs_freq MHz"
        ;;
esac

dfs_escape() {
    printf '%s' "$1" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g'
}

# Never sample a workstation's radio just because a remote event names wlan0.
# Native on-node callers explicitly select the local interface. This reads
# driver survey data only: no scans, tuning, service changes or RF transmission.
dfs_noise='Channel noise: not sampled (no local radio selected).'
dfs_noise_iface=${DFS_BANNER_NOISE_IFACE:-}
if [ -n "$dfs_noise_iface" ]; then
    case "$dfs_noise_iface" in
        *[!A-Za-z0-9_.-]*) printf '%s\n' 'dfs_banner: invalid noise interface' >&2; exit 2 ;;
    esac
    [ "${#dfs_noise_iface}" -le 15 ] || exit 2
    dfs_noise="Channel noise: unavailable on $dfs_noise_iface (no valid active-channel survey)."

    dfs_radio_identity() {
        awk '
            $1 == "ifindex" { idx = $2 }
            $1 == "wdev" { dev = $2 }
            $1 == "channel" && $2 ~ /^-?[0-9]+$/ && $3 ~ /^\([0-9]+$/ && $4 == "MHz)," {
                channel = $2; freq = substr($3, 2); count++
            }
            END { if (count == 1 && idx ~ /^[0-9]+$/ && dev ~ /^0x[0-9a-f]+$/)
                print channel, freq, idx, dev }
        '
    }

    if dfs_info=$(iw dev "$dfs_noise_iface" info 2>/dev/null) &&
       dfs_before=$(printf '%s\n' "$dfs_info" | dfs_radio_identity) &&
       [ -n "$dfs_before" ] &&
       dfs_survey=$(iw dev "$dfs_noise_iface" survey dump 2>/dev/null) &&
       dfs_info=$(iw dev "$dfs_noise_iface" info 2>/dev/null) &&
       dfs_after=$(printf '%s\n' "$dfs_info" | dfs_radio_identity) &&
       [ "$dfs_before" = "$dfs_after" ]; then
        dfs_noise_channel=${dfs_before%% *}
        dfs_rest=${dfs_before#* }
        dfs_noise_freq=${dfs_rest%% *}
        # Do not use the first survey entry, or a cached entry for the radar
        # frequency after the radio has moved. Reject ambiguous/invalid data.
        dfs_dbm=$(printf '%s\n' "$dfs_survey" | awk -v freq="$dfs_noise_freq" '
            $1 == "Survey" { selected = 0 }
            $1 == "frequency:" {
                if ($4 == "[in" && $5 == "use]") inuse++
                selected = ($2 == freq && $3 == "MHz" && $4 == "[in" && $5 == "use]")
                if (selected) matches++
            }
            selected && $1 == "noise:" {
                values++
                if ($2 ~ /^-[0-9]+$/ && $2 >= -150 && $2 < 0 && $3 == "dBm") {
                    noise = $2; valid++
                }
            }
            END { if (inuse == 1 && matches == 1 && values == 1 && valid == 1) print noise }
        ')
        if [ -n "$dfs_dbm" ]; then
            dfs_noise_time=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
            dfs_noise="Channel noise: $dfs_dbm dBm - channel $dfs_noise_channel ($dfs_noise_freq MHz), $dfs_noise_iface. Read $dfs_noise_time; source iw survey (driver snapshot)."
            if [ "$dfs_mode" = demo ]; then
                dfs_noise="$dfs_noise Real radio reading; separate from the simulated radar report."
            elif [ "$dfs_noise_iface" != "$dfs_iface" ] || [ "$dfs_noise_freq" != "$dfs_freq" ]; then
                dfs_noise="$dfs_noise Not a measurement of the reported radar channel/interface."
            else
                dfs_noise="$dfs_noise Read after the report, not a radar-pulse measurement."
            fi
        fi
    fi
fi
dfs_noise=$(dfs_escape "$dfs_noise")
dfs_node=$(dfs_escape "$dfs_node")
dfs_iface=$(dfs_escape "$dfs_iface")
dfs_source=$(dfs_escape "$dfs_source")
dfs_when=$(dfs_escape "$dfs_when")

[ ! -L "$dfs_messages" ] || { printf '%s\n' 'dfs_banner: refusing symlink directory' >&2; exit 2; }
[ ! -L "$dfs_output" ] || { printf '%s\n' 'dfs_banner: refusing symlink message' >&2; exit 2; }
mkdir -p "$dfs_messages"

# Staging is a private child directory on the same filesystem. AREDN readfile()
# returns null for directories, so incomplete/duplicate messages are not shown.
dfs_stage=$(mktemp -d "$dfs_messages/.aredn-dfs-stage.XXXXXX")
trap 'rm -f -- "$dfs_stage/message"; rmdir -- "$dfs_stage"' 0
trap 'exit 130' INT
trap 'exit 143' TERM

# Keep the native <strong>&#8611; LABEL:</strong>...<p> envelope on ONE line.
# Do not put another <strong> inside the body: the native reader splits on it.
printf '%s\n' "<strong>&#8611; DFS detection test:</strong><b>$dfs_heading</b> - channel $dfs_channel ($dfs_frequency), $dfs_node / $dfs_iface.<br>Received $dfs_when; source $dfs_source.<br>$dfs_noise<br>$dfs_note<p>" > "$dfs_stage/message"
chmod 644 "$dfs_stage/message"
mv -fT "$dfs_stage/message" "$dfs_output"
