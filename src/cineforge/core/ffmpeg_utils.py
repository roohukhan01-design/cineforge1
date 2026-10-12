"""Locate FFmpeg and inspect media files."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


class FFmpegError(Exception):
    """Any problem running or locating FFmpeg."""


def popen_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def find_ffmpeg() -> str | None:
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates: list[Path] = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(Path(base) / exe)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / exe)
    for c in candidates:
        if c.is_file():
            return str(c)
    env = os.environ.get("CINEFORGE_FFMPEG")
    if env and Path(env).is_file():
        return env
    return shutil.which("ffmpeg")


def require_ffmpeg() -> str:
    ff = find_ffmpeg()
    if not ff:
        raise FFmpegError(
            "FFmpeg was not found. Reinstall CineForge (the installer includes FFmpeg) "
            "or put ffmpeg on your PATH."
        )
    return ff


def _run_text(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=popen_flags(), timeout=timeout,
    )


def check_encoders(ffmpeg: str) -> list[str]:
    """Return a list of problems (empty when libx264 + aac are available)."""
    out = _run_text([ffmpeg, "-hide_banner", "-encoders"]).stdout
    problems = []
    if "libx264" not in out:
        problems.append("This FFmpeg build has no libx264 encoder.")
    if " aac " not in out:
        problems.append("This FFmpeg build has no AAC encoder.")
    return problems


@dataclass
class MediaInfo:
    path: str
    duration: float | None
    has_video: bool
    has_audio: bool
    width: int = 0
    height: int = 0

    @property
    def is_image(self) -> bool:
        return Path(self.path).suffix.lower() in IMAGE_EXT


def probe(path: str, ffmpeg: str | None = None) -> MediaInfo:
    p = Path(path)
    if not p.is_file():
        raise FFmpegError(f"File not found: {path}")
    ff = ffmpeg or require_ffmpeg()
    try:
        err = _run_text([ff, "-hide_banner", "-nostdin", "-i", str(p)]).stderr
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"Timed out reading {p.name}.")
    has_video = ": Video:" in err
    has_audio = ": Audio:" in err
    if not (has_video or has_audio):
        raise FFmpegError(f"{p.name} is not a readable media file.")
    dur = None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    w = h = 0
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", err)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
    return MediaInfo(str(p), dur, has_video, has_audio, w, h)
