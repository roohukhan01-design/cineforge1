"""Headless end-to-end self test used by CI and `CineForge.exe --selftest out.mp4`."""
from __future__ import annotations

import subprocess
import tempfile
import traceback
from pathlib import Path

from .ffmpeg_utils import popen_flags, probe, require_ffmpeg
from .project import Project, Scene, Settings
from .renderer import Renderer


def make_sample_assets(folder: str, ffmpeg: str) -> dict[str, str]:
    d = Path(folder)
    jobs = {
        "img1": (["-f", "lavfi", "-i", "testsrc2=s=640x360:d=1", "-frames:v", "1"], "a.png"),
        "img2": (["-f", "lavfi", "-i", "smptebars=s=640x360:d=1", "-frames:v", "1"], "b.png"),
        "clip": (["-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3", "-c:v", "libx264",
                  "-pix_fmt", "yuv420p"], "c.mp4"),
        "voice": (["-f", "lavfi", "-i", "sine=frequency=440:duration=3"], "voice.wav"),
        "music": (["-f", "lavfi", "-i", "sine=frequency=220:duration=5"], "music.wav"),
    }
    out = {}
    for key, (args, name) in jobs.items():
        target = str(d / name)
        r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", *args, target],
                           capture_output=True, text=True, creationflags=popen_flags())
        if r.returncode != 0:
            raise RuntimeError(f"Could not create sample {name}: {r.stderr}")
        out[key] = target
    return out


def build_sample_project(assets: dict[str, str], output: str) -> Project:
    st = Settings(width=640, height=360, fps=25, transition="fade", transition_duration=0.5,
                  color="cinematic", music=assets["music"], music_volume=0.3,
                  subtitles=True, burn_subtitles=True)
    scenes = [
        Scene("Welcome to CineForge. This is a self test.", assets["img1"], assets["voice"], 3.0),
        Scene("A video clip scene with a subtitle.", assets["clip"], "", 3.0),
        Scene("Final scene using another image.", assets["img2"], "", 3.0),
    ]
    return Project(script="selftest", scenes=scenes, settings=st, output=output)


def run_selftest(out_path: str) -> int:
    log: list[str] = []
    code = 1
    try:
        ff = require_ffmpeg()
        log.append(f"ffmpeg: {ff}")
        with tempfile.TemporaryDirectory(prefix="cf_selftest_") as tmp:
            assets = make_sample_assets(tmp, ff)
            proj = build_sample_project(assets, out_path)
            Renderer(proj, out_path, ffmpeg=ff, log=log.append).run()
        info = probe(out_path, ff)
        log.append(f"output: duration={info.duration}s video={info.has_video} "
                   f"audio={info.has_audio} size={info.width}x{info.height}")
        if info.has_video and info.has_audio:
            log.append("SELFTEST PASSED")
            code = 0
        else:
            log.append("SELFTEST FAILED: missing stream")
    except Exception:
        log.append("SELFTEST FAILED\n" + traceback.format_exc())
    try:
        Path(out_path + ".log").write_text("\n".join(log), encoding="utf-8")
    except OSError:
        pass
    return code
