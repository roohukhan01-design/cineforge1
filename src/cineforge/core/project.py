"""Project model, persistence and script splitting."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

PROJECT_VERSION = 1
RESOLUTIONS = [
    ("1920x1080 - Landscape HD", 1920, 1080),
    ("1280x720 - Landscape 720p", 1280, 720),
    ("1080x1920 - Vertical (Shorts/Reels)", 1080, 1920),
    ("1080x1080 - Square", 1080, 1080),
]
TRANSITIONS = ["none", "fade", "dissolve", "fadeblack", "wipeleft", "slideleft"]
COLOR_PRESETS = ["none", "cinematic", "warm", "cool", "vivid", "bw"]


class ProjectError(Exception):
    pass


@dataclass
class Scene:
    text: str = ""
    media: str = ""
    voice: str = ""
    duration: float = 4.0


@dataclass
class Settings:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    transition: str = "none"
    transition_duration: float = 0.5
    color: str = "none"
    fade_in: float = 0.5
    fade_out: float = 0.5
    music: str = ""
    music_volume: float = 0.25
    voice_volume: float = 1.0
    duck_music: bool = True
    subtitles: bool = True
    burn_subtitles: bool = True
    sub_max_chars: int = 42
    sub_offset: float = 0.0


@dataclass
class Project:
    script: str = ""
    scenes: list[Scene] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    output: str = ""


def estimate_duration(text: str) -> float:
    words = len(text.split())
    return round(max(2.5, words / 2.5), 1)


def split_script(text: str, max_chars: int = 160) -> list[str]:
    """Split a script into scene texts: blank-line paragraphs, else grouped sentences."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if p]
    if len(paras) > 1:
        return paras
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", paras[0]) if s]
    scenes, cur = [], ""
    for s in sentences:
        if cur and len(cur) + 1 + len(s) > max_chars:
            scenes.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        scenes.append(cur)
    return scenes


def scenes_from_script(text: str) -> list[Scene]:
    return [Scene(text=t, duration=estimate_duration(t)) for t in split_script(text)]


def scene_starts(durations: list[float], transition: float) -> list[float]:
    t = max(0.0, transition)
    return [sum(durations[:i]) - i * t for i in range(len(durations))]


def total_duration(durations: list[float], transition: float) -> float:
    if not durations:
        return 0.0
    return sum(durations) - (len(durations) - 1) * max(0.0, transition)


def _pick(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


def save_project(project: Project, path: str) -> None:
    data = {"version": PROJECT_VERSION, **asdict(project)}
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except OSError as e:
        raise ProjectError(f"Could not save project: {e}") from e


def load_project(path: str) -> Project:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"Project file not found: {path}")
    except (OSError, ValueError) as e:
        raise ProjectError(f"Could not read project file: {e}")
    if not isinstance(data, dict) or "scenes" not in data:
        raise ProjectError("This file is not a CineForge project.")
    if data.get("version", 0) > PROJECT_VERSION:
        raise ProjectError("This project was made with a newer version of CineForge.")
    try:
        scenes = [_pick(Scene, s) for s in data.get("scenes", [])]
        settings = _pick(Settings, data.get("settings", {}))
        return Project(script=data.get("script", ""), scenes=scenes,
                       settings=settings, output=data.get("output", ""))
    except (TypeError, ValueError, AttributeError) as e:
        raise ProjectError(f"Project file is damaged: {e}")
