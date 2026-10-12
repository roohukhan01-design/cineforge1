import threading
import time
from pathlib import Path

import pytest

from cineforge.core import subtitles
from cineforge.core.ffmpeg_utils import find_ffmpeg, probe
from cineforge.core.project import (Project, Scene, Settings, load_project, save_project,
                                    scene_starts, split_script, total_duration, ProjectError)
from cineforge.core.renderer import RenderCancelled, RenderError, Renderer
from cineforge.core.selftest import make_sample_assets, build_sample_project

needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not available")


def test_split_paragraphs():
    assert split_script("One.\n\nTwo line\nwrapped.\n\n\nThree.") == ["One.", "Two line wrapped.", "Three."]


def test_split_sentences_grouping():
    text = " ".join(f"Sentence number {i} is here." for i in range(10))
    parts = split_script(text, max_chars=60)
    assert len(parts) > 3 and all(len(p) <= 60 for p in parts)


def test_split_empty():
    assert split_script("  \n ") == []


def test_timing_math():
    assert scene_starts([3, 3, 3], 0.5) == [0, 2.5, 5.0]
    assert total_duration([3, 3, 3], 0.5) == 8.0
    assert total_duration([], 0.5) == 0.0


def test_srt_format():
    srt = subtitles.build_srt(["Hello world"], [0.0], [2.0])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,950\nHello world")
    assert subtitles.fmt_time(3661.5) == "01:01:01,500"


def test_project_roundtrip(tmp_path):
    p = Project(script="s", scenes=[Scene("a", "x.png", "v.wav", 5.5)],
                settings=Settings(transition="fade", music="m.mp3"), output="o.mp4")
    f = tmp_path / "p.cforge"
    save_project(p, str(f))
    q = load_project(str(f))
    assert q == p


def test_load_errors(tmp_path):
    with pytest.raises(ProjectError):
        load_project(str(tmp_path / "missing.cforge"))
    bad = tmp_path / "bad.cforge"
    bad.write_text("not json")
    with pytest.raises(ProjectError):
        load_project(str(bad))
    bad.write_text('{"hello": 1}')
    with pytest.raises(ProjectError):
        load_project(str(bad))


@needs_ffmpeg
def test_validation_messages(tmp_path):
    p = Project(scenes=[Scene("a", str(tmp_path / "nope.png"), "", 1.0)],
                settings=Settings(transition="fade", transition_duration=0.9,
                                  music=str(tmp_path / "nomusic.mp3")))
    errs = Renderer(p, str(tmp_path / "o.txt")).validate()
    text = "\n".join(errs)
    assert "media file is missing" in text
    assert "Background music file is missing" in text
    assert "longer than half" in text
    assert ".mp4" in text
    assert Renderer(Project(), str(tmp_path / "o.mp4")).validate()[0].startswith("Add at least")


@needs_ffmpeg
def test_end_to_end_render(tmp_path):
    ff = find_ffmpeg()
    assets = make_sample_assets(str(tmp_path), ff)
    out = tmp_path / "out" / "video.mp4"
    proj = build_sample_project(assets, str(out))
    progress = []
    Renderer(proj, str(out), progress=lambda f, m: progress.append(f)).run()
    info = probe(str(out), ff)
    assert info.has_video and info.has_audio
    assert (info.width, info.height) == (640, 360)
    assert abs(info.duration - 8.0) < 0.5
    assert out.with_suffix(".srt").is_file()
    assert progress and progress[-1] == 1.0 and progress == sorted(progress)


@needs_ffmpeg
def test_render_without_audio_or_subtitles(tmp_path):
    ff = find_ffmpeg()
    assets = make_sample_assets(str(tmp_path), ff)
    p = Project(scenes=[Scene("x", assets["img1"], "", 2.0), Scene("", "", "", 2.0)],
                settings=Settings(width=320, height=180, fps=24, subtitles=False))
    out = tmp_path / "plain.mp4"
    Renderer(p, str(out)).run()
    info = probe(str(out), ff)
    assert info.has_video and not info.has_audio
    assert abs(info.duration - 4.0) < 0.5


@needs_ffmpeg
def test_cancel(tmp_path):
    ff = find_ffmpeg()
    assets = make_sample_assets(str(tmp_path), ff)
    proj = build_sample_project(assets, str(tmp_path / "cancelled_out.mp4"))
    r = Renderer(proj, str(tmp_path / "cancelled_out.mp4"))
    result = {}

    def work():
        try:
            r.run()
            result["ok"] = True
        except RenderCancelled:
            result["cancelled"] = True

    th = threading.Thread(target=work)
    th.start()
    time.sleep(0.3)
    r.cancel()
    th.join(30)
    assert result.get("cancelled")
    assert not (tmp_path / "cancelled_out.mp4").exists()


@needs_ffmpeg
def test_probe_bad_file(tmp_path):
    bad = tmp_path / "x.mp4"
    bad.write_text("garbage")
    with pytest.raises(Exception):
        probe(str(bad))
