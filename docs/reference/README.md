# Source provenance

The JSON manifests retain pinned upstream URLs, revisions and SHA-256 hashes
from the original protocol review. They describe hostapd/control/action behavior,
OpenWrt ubus notifications and native ubus CLI output. They are not hashes of
the intended node's installed firmware, and do not establish field capability.

Source can be retrieved from the recorded public upstream revisions. Original
downloaded source copies remain in the owner's private prototype backup/evidence;
private measurements are not included in this repository. The project does not
compile or ship those upstream implementations inside its APK.

`banner-provenance.json` pins the AREDN message reader and template used by the
native consumer fixtures. The tests preserve their function/template bodies and
replace only imports/filesystem dependencies with isolated bindings. Supply
the pinned source and a native ucode runtime as described in [BUILD.md](../../BUILD.md).
