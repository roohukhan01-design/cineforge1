"""Stage the pinned FFmpeg binary and license texts for packaging (run in CI)."""
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg

build = Path("build")
(build / "licenses").mkdir(parents=True, exist_ok=True)
src = imageio_ffmpeg.get_ffmpeg_exe()
dst = build / "ffmpeg.exe"
shutil.copy2(src, dst)


def run(*args):
    return subprocess.run([str(dst), "-hide_banner", *args], capture_output=True, text=True).stdout


version = run("-version")
(build / "ffmpeg-buildinfo.txt").write_text(version, encoding="utf-8")
print(version.splitlines()[0])
print([l for l in version.splitlines() if l.startswith("configuration")][:1])
if "libx264" not in run("-encoders"):
    sys.exit("Bundled FFmpeg has no libx264 encoder")
filters = run("-filters")
if " xfade " not in filters:
    sys.exit("Bundled FFmpeg is too old: it has no 'xfade' filter (needs FFmpeg 4.3+)")
if "normalize" not in run("-h", "filter=amix"):
    sys.exit("Bundled FFmpeg is too old: 'amix' has no 'normalize' option (needs FFmpeg 4.4+)")
if " subtitles " not in filters:
    print("WARNING: bundled FFmpeg has no 'subtitles' filter; CineForge will fall back to soft subtitles")

# Each license has two sources; every source is tried 3 times before giving up.
LICENSES = {
    "GPL-2.0.txt": [
        "https://raw.githubusercontent.com/spdx/license-list-data/main/text/GPL-2.0-only.txt",
        "https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt",
    ],
    "GPL-3.0.txt": [
        "https://raw.githubusercontent.com/spdx/license-list-data/main/text/GPL-3.0-only.txt",
        "https://www.gnu.org/licenses/gpl-3.0.txt",
    ],
    "LGPL-3.0.txt": [
        "https://raw.githubusercontent.com/spdx/license-list-data/main/text/LGPL-3.0-only.txt",
        "https://www.gnu.org/licenses/lgpl-3.0.txt",
    ],
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "CineForge-build"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 5000:
        raise ValueError(f"suspiciously small download ({len(data)} bytes)")
    return data


for name, urls in LICENSES.items():
    data, last_err = None, None
    for url in urls:
        for attempt in range(3):
            try:
                data = fetch(url)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"retry {name} ({url}, attempt {attempt + 1}): {e}")
                time.sleep(2)
        if data:
            break
    if not data:
        sys.exit(f"Could not download {name}: {last_err}")
    (build / "licenses" / name).write_bytes(data)
    print("downloaded", name)
