# Alternative capture paths (Python stays off the node)

Use one source per radio. The APK provides the hostapd_cli relay path described
in [INSTALL.md](INSTALL.md). Existing logs or native ubus may already provide the
needed evidence without an extra service. None of these recipes constitutes
live validation or initiates a deployment by itself.

## Existing logs

From this repository on the monitoring computer, using Bash and an authorized
SSH alias:

```sh
set -o pipefail
ssh -T field-ap 'logread -f' | python3 dfs_detector.py --node field-ap
python3 dfs_detector.py --node field-ap --summary saved-logread.txt
```

If using the APK's relay, add `--relay-only` so native originals and relayed
copies are not counted together. Preserve SSH stderr and process status. Silence
is not proof of a healthy source or the absence of radar.

## Temporary action relay without installing the APK

Verify `hostapd_cli`, `logger`, the AP interface and control socket first. Copy
only `dfs_action.sh` to an authorized temporary path, mark it executable, then
run in the foreground (example socket/interface only):

```sh
hostapd_cli -p /var/run/hostapd -i wlan0 -a /tmp/dfs_action.sh
```

Read `logread -f` off-node with `--relay-only`. Do not run this alongside the APK
service. The action preserves every event argument after the interface and
logs only exact accepted tokens. Its PID helps distinguish same-second records.
Without banner output, the helper writes no state files, but logger follows existing syslog retention
and forwarding. Stop the foreground CLI and remove your temporary helper when
finished. A zero CLI exit or running process does not guarantee healthy delivery;
in reviewed upstream code PING loss can exit zero and action errors are not
propagated. See [DETECTION.md](DETECTION.md).

For the r2 detection-test banner, also stage executable `dfs_banner.sh` and set
`DFS_BANNER_HELPER=/tmp/dfs_banner.sh` in the foreground CLI environment. Only
explicit radar reports update the message and read the event interface's passive
current-channel noise. Readings are timestamped snapshots, not continuous noise
monitoring or radar-pulse measurements. See [BANNER.md](BANNER.md) for selection,
simulation separation and scoped cleanup.

## Native ubus subscription

Discover the correct object on the node with `ubus list 'hostapd.*'`. The reviewed
OpenWrt source uses object notifications, **not broadcast events**, so use
`subscribe`, not `listen`. Object presence alone does not prove event capability.

```sh
set -o pipefail
ssh -T field-ap 'ubus -t 60 subscribe hostapd.wlan0' | \
  python3 dfs_detector.py --node field-ap --ubus-object hostapd.wlan0 --summary
```

This is a bounded capture. For intended continuous streaming omit `-t 60` and
`--summary`. A supported notification is one JSON object per line:

```json
{"radar-detected":{"frequency":5660,"width":2,"center1":5670,"center2":0}}
```

Use exactly one object per stream: the CLI does not include source-object
identity, so `--ubus-object` records the operator-selected source. Multiple BSS
notifications can represent one radio event. The CLI can stay alive after an
object is removed and does not guarantee automatic resubscription; preserve
coverage gaps and check source state separately. Invalid/truncated JSON or
conflicting interfaces fail visibly. `channel-switch` is context only.

## Optional Python local-socket capture

Only on a host with Python and the **local** per-interface hostapd UNIX socket:

```sh
python3 dfs_detector.py --node field-ap --interface wlan0 \
  --control-socket /var/run/hostapd/wlan0 \
  > radar-events.jsonl 2> collector-status.log
```

Both Python modules must be present. This is not a remote IP/URL interface and
Python is not bundled in the APK. The collector uses ATTACH/PING/DETACH only;
strict acknowledgements, deadlines, private peer-bound sockets and cleanup are
tested against synthetic peers. Source loss exits nonzero; no automatic
reconnection, historical replay or radio changes occur.
