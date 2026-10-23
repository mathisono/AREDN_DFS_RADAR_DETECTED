"""Run exact AREDN message-reader/template bodies with isolated filesystem imports.

No device configuration, network access or production message path is used.
Requires an external native ucode interpreter and an AREDN source checkout.
"""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def render_native(ucode, source_root, fixture_root):
    source_root = Path(source_root)
    reader = source_root / "files/usr/share/ucode/aredn/messages.uc"
    template = source_root / "files/app/partial/messages.ut"
    source = reader.read_text()
    source = re.sub(r'^import \* as \w+ from "[^"]+";\n', '', source, flags=re.M)
    source = source.replace("export function ", "function ")
    wrappers = '''// Fixture-only import substitution; original function bodies follow.
import * as realfs from "fs";
const fixture_root = ARGV[0];
const fs = {
    access: path => realfs.access(fixture_root + path),
    readfile: path => realfs.readfile(fixture_root + path),
    opendir: path => realfs.opendir(fixture_root + path)
};
const configuration = { getName: () => "fixture-node" };
const uci = {}, hardware = {}, lqm = {}, radios = {};
'''
    program = wrappers + source + '''
const found = getMessages();
const original = json(sprintf("%J", found));
const html = render(ARGV[1], {
    inner: { msgs: found, todos: [], alerts: [] }, auth: { isAdmin: false }
});
printf("%J\\n", { messages: original, html: html });
'''
    with tempfile.TemporaryDirectory(prefix="dfs-native-render-", dir="/tmp") as runtime:
        script = Path(runtime) / "messages-fixture.uc"
        script.write_text(program)
        result = subprocess.run([str(ucode), str(script), str(fixture_root), str(template)],
                                text=True, capture_output=True, timeout=5, check=True)
    rendered = json.loads(result.stdout)
    rendered["reader_sha256"] = hashlib.sha256(reader.read_bytes()).hexdigest()
    rendered["template_sha256"] = hashlib.sha256(template.read_bytes()).hexdigest()
    return rendered
