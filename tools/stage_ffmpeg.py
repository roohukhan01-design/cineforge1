"""Stage the pinned FFmpeg binary and license texts for packaging (run in CI)."""
import shutil
import subprocess
import sys
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

LICENSES = {
    "GPL-2.0.txt": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt",
    "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
    "LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
}
for name, url in LICENSES.items():
    with urllib.request.urlopen(url, timeout=60) as r:
        (build / "licenses" / name).write_bytes(r.read())
    print("downloaded", name)
