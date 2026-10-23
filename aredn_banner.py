"""Opt-in local AREDN banner sink, shared with the native shell action path."""

import os
from pathlib import Path
import subprocess


class BannerSink:
    def __init__(self, directory):
        self.directory = Path(directory)
        if not self.directory.is_absolute():
            raise ValueError("--banner-dir must be an absolute local directory")
        self.helper = Path(__file__).with_name("dfs_banner.sh")

    def emit(self, event):
        # Never infer a flag from a channel change, CAC, failures or low rates.
        if not event.get("flag_channel") or event.get("classification") != "radar_reported":
            return False
        freq = event.get("reported_frequency_mhz")
        if freq is not None and (type(freq) is not int or freq <= 0):
            raise ValueError("banner frequency must be a positive integer or unknown")
        env = dict(os.environ, DFS_BANNER_DIR=str(self.directory),
                   DFS_BANNER_OBSERVED_AT=event["ingested_at_utc"],
                   # This sink may consume remote logs. Do not mislabel a local
                   # workstation survey as a measurement of the event's node.
                   DFS_BANNER_NOISE_IFACE="")
        result = subprocess.run(
            [str(self.helper), "report", event["node"], event.get("interface") or "unknown",
             str(freq) if freq is not None else "unknown", event["source"]],
            env=env, text=True, capture_output=True, timeout=5,
        )
        if result.returncode:
            raise OSError(f"banner update failed ({result.returncode}): {result.stderr.strip()}")
        return True
