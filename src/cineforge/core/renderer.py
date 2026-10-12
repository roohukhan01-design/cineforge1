"""FFmpeg-based renderer: per-scene segments -> transitions/effects/audio mix -> MP4."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from .ffmpeg_utils import (IMAGE_EXT, FFmpegError, check_encoders, popen_flags,
                           probe, require_ffmpeg)
from .project import Project, scene_starts, total_duration
from .subtitles import build_srt

COLOR_FILTERS = {
    "none": "",
    "cinematic": "eq=contrast=1.1:saturation=0.92,colorbalance=bs=0.05:rh=0.05:bh=-0.04,vignette=PI/5",
    "warm": "colorbalance=rm=0.06:bm=-0.05,eq=saturation=1.1",
    "cool": "colorbalance=bm=0.06:rm=-0.04",
    "vivid": "eq=saturation=1.4:contrast=1.08",
    "bw": "hue=s=0,eq=contrast=1.15",
}


class RenderError(Exception):
    """User-facing render problem."""


class RenderCancelled(Exception):
    pass


class FFmpegFailed(RenderError):
    pass


def explain(stderr: str) -> str:
    s = stderr.strip()
    low = s.lower()
    hints = [
        ("no such file", "A file could not be found. Check that all media still exists."),
        ("permission denied", "Permission denied. Choose an output folder you can write to."),
        ("no space left", "The disk is full. Free some space or choose another drive."),
        ("invalid data found", "A media file looks corrupt or is not a valid media file."),
        ("subtitles", "Subtitle rendering failed."),
    ]
    for key, msg in hints:
        if key in low:
            return f"{msg}\n\nFFmpeg said:\n{s[-800:]}"
    return f"FFmpeg failed.\n\n{s[-800:]}"


class Renderer:
    def __init__(self, project: Project, output: str, ffmpeg: Optional[str] = None,
                 progress: Optional[Callable[[float, str], None]] = None,
                 log: Optional[Callable[[str], None]] = None):
        self.project = project
        self.output = output
        self.ffmpeg = ffmpeg
        self._progress = progress or (lambda f, m: None)
        self._log = log or (lambda m: None)
        self._cancel = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.work = ""
        self._acc = 0.0
        self._W = 1.0

    # ---- control -------------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except OSError:
                    pass

    # ---- validation ----------------------------------------------------
    def validate(self) -> list[str]:
        p, s = self.project, self.project.settings
        errs: list[str] = []
        if not p.scenes:
            errs.append("Add at least one scene.")
        for i, sc in enumerate(p.scenes, 1):
            if sc.duration < 0.5:
                errs.append(f"Scene {i}: duration must be at least 0.5 seconds.")
            for label, path in (("media", sc.media), ("voice recording", sc.voice)):
                if path and not Path(path).is_file():
                    errs.append(f"Scene {i}: {label} file is missing: {path}")
        if s.music and not Path(s.music).is_file():
            errs.append(f"Background music file is missing: {s.music}")
        if s.transition != "none" and p.scenes:
            if s.transition_duration <= 0:
                errs.append("Transition length must be greater than 0.")
            elif s.transition_duration > min(sc.duration for sc in p.scenes) / 2:
                errs.append("Transition is longer than half of the shortest scene. "
                            "Shorten the transition or lengthen the scenes.")
        out = self.output.strip()
        if not out:
            errs.append("Choose an output file.")
        else:
            if Path(out).suffix.lower() != ".mp4":
                errs.append("Output file must end in .mp4.")
            parent = Path(out).expanduser().resolve().parent
            try:
                parent.mkdir(parents=True, exist_ok=True)
                if not os.access(parent, os.W_OK):
                    errs.append(f"Output folder is not writable: {parent}")
            except OSError as e:
                errs.append(f"Output folder cannot be created: {e}")
        try:
            ff = self.ffmpeg or require_ffmpeg()
            self.ffmpeg = ff
            errs.extend(check_encoders(ff))
        except FFmpegError as e:
            errs.append(str(e))
        return errs

    # ---- main entry ----------------------------------------------------
    def run(self) -> str:
        errs = self.validate()
        if errs:
            raise RenderError("\n".join(errs))
        p, s = self.project, self.project.settings
        durs = [sc.duration for sc in p.scenes]
        t = s.transition_duration if s.transition != "none" else 0.0
        total = total_duration(durs, t)
        self._W = sum(durs) + 0.7 * total
        self._acc = 0.0
        out = Path(self.output).expanduser().resolve()
        self.work = tempfile.mkdtemp(prefix="cineforge_")
        try:
            segs = []
            for i, sc in enumerate(p.scenes):
                self._check()
                self._log(f"Rendering scene {i + 1}/{len(p.scenes)}...")
                seg = str(Path(self.work) / f"seg{i:03}.mp4")
                self._run(self._segment_args(sc, seg), sc.duration, sc.duration,
                          f"Scene {i + 1}/{len(p.scenes)}")
                segs.append(seg)
            srt_text = ""
            if s.subtitles:
                srt_text = build_srt([sc.text for sc in p.scenes], scene_starts(durs, t),
                                     durs, s.sub_max_chars, s.sub_offset, total)
                if srt_text.strip():
                    (Path(self.work) / "subs.srt").write_text(srt_text, encoding="utf-8")
            final = str(Path(self.work) / "final.mp4")
            self._log("Mixing and encoding final video...")
            burn = s.burn_subtitles and bool(srt_text.strip())
            try:
                self._final(segs, final, total, t, srt_text, burn)
            except FFmpegFailed as e:
                if not burn:
                    raise
                self._log("Burned-in subtitles failed; retrying with a selectable "
                          "subtitle track instead.\n" + str(e).splitlines()[0])
                self._final(segs, final, total, t, srt_text, False)
            self._check()
            voices, has_music = self._audio_plan()
            self._validate_output(final, total, bool(voices) or has_music)
            shutil.move(final, str(out))
            if srt_text.strip():
                out.with_suffix(".srt").write_text(srt_text, encoding="utf-8")
            self._progress(1.0, "Done")
            self._log(f"Saved {out}")
            return str(out)
        finally:
            shutil.rmtree(self.work, ignore_errors=True)

    # ---- helpers -------------------------------------------------------
    def _check(self):
        if self._cancel.is_set():
            raise RenderCancelled()

    def _audio_plan(self):
        voices = [(i, sc) for i, sc in enumerate(self.project.scenes) if sc.voice]
        return voices, bool(self.project.settings.music)

    def _segment_args(self, sc, out: str) -> list[str]:
        s = self.project.settings
        W, H, fps = s.width, s.height, s.fps
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p")
        if not sc.media:
            inp = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={fps}"]
        elif Path(sc.media).suffix.lower() in IMAGE_EXT:
            inp = ["-loop", "1", "-framerate", str(fps), "-i", sc.media]
        else:
            inp = ["-stream_loop", "-1", "-i", sc.media]
        return [*inp, "-t", f"{sc.duration:.3f}", "-vf", vf, "-an", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-r", str(fps), out]

    def _final(self, segs, out, total, t, srt_text, burn):
        p, s = self.project, self.project.settings
        n = len(segs)
        args: list[str] = []
        for seg in segs:
            args += ["-i", seg]
        idx = n
        # video graph
        if n == 1:
            parts = ["[0:v]null[vc]"]
        elif t > 0:
            parts, prev = [], "[0:v]"
            durs = [sc.duration for sc in p.scenes]
            for k in range(1, n):
                off = sum(durs[:k]) - k * t
                lab = f"[x{k}]" if k < n - 1 else "[vc]"
                parts.append(f"{prev}[{k}:v]xfade=transition={s.transition}:"
                             f"duration={t}:offset={off:.3f}{lab}")
                prev = lab
        else:
            parts = ["".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]"]
        vf = []
        if COLOR_FILTERS.get(s.color):
            vf.append(COLOR_FILTERS[s.color])
        if s.fade_in > 0:
            vf.append(f"fade=t=in:st=0:d={s.fade_in}")
        if s.fade_out > 0:
            vf.append(f"fade=t=out:st={max(0.0, total - s.fade_out):.3f}:d={s.fade_out}")
        if burn:
            vf.append("subtitles=subs.srt:force_style='FontSize=16,Outline=2,Shadow=0,MarginV=24'")
        vf.append("format=yuv420p")
        parts.append("[vc]" + ",".join(vf) + "[vout]")
        # audio graph
        voices, has_music = self._audio_plan()
        vl = []
        for k, (i, sc) in enumerate(voices):
            args += ["-i", sc.voice]
            ms = int(round(scene_starts([x.duration for x in p.scenes], t)[i] * 1000))
            parts.append(f"[{idx}:a]atrim=duration={sc.duration:.3f},asetpts=PTS-STARTPTS,"
                         f"adelay=delays={ms}:all=1,volume={s.voice_volume}[va{k}]")
            vl.append(f"[va{k}]")
            idx += 1
        if voices:
            parts.append("".join(vl) + f"amix=inputs={len(voices)}:duration=longest:normalize=0[voice]")
        if has_music:
            args += ["-stream_loop", "-1", "-i", s.music]
            parts.append(f"[{idx}:a]atrim=duration={total:.3f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d=1,afade=t=out:st={max(0.0, total - 2):.3f}:d=2,"
                         f"volume={s.music_volume}[mus]")
            idx += 1
        if voices and has_music and s.duck_music:
            parts.append(f"[voice]apad=whole_dur={total:.3f},asplit=2[vm][vs]")
            parts.append("[mus][vs]sidechaincompress=threshold=0.03:ratio=10:attack=20:"
                         "release=400:makeup=1[duck]")
            parts.append("[vm][duck]amix=inputs=2:duration=longest:normalize=0[aout]")
        elif voices and has_music:
            parts.append("[voice][mus]amix=inputs=2:duration=longest:normalize=0[aout]")
        elif voices:
            parts.append("[voice]anull[aout]")
        elif has_music:
            parts.append("[mus]anull[aout]")
        has_audio = bool(voices) or has_music
        soft = bool(srt_text.strip()) and not burn
        if soft:
            args += ["-i", str(Path(self.work) / "subs.srt")]
        cmd = [*args, "-filter_complex", ";".join(parts), "-map", "[vout]"]
        if has_audio:
            cmd += ["-map", "[aout]"]
        if soft:
            cmd += ["-map", f"{idx}:s", "-c:s", "mov_text"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-r", str(s.fps)]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        cmd += ["-movflags", "+faststart", "-t", f"{total:.3f}", out]
        self._run(cmd, total, 0.7 * total, "Encoding")

    def _run(self, args, expected, weight, label):
        cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
               "-progress", "pipe:1", "-nostats", *args]
        errpath = Path(self.work) / "ffmpeg_err.txt"
        with open(errpath, "w", encoding="utf-8", errors="replace") as ef:
            with self._lock:
                if self._cancel.is_set():
                    raise RenderCancelled()
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=ef, text=True, encoding="utf-8",
                    errors="replace", cwd=self.work, creationflags=popen_flags())
            proc = self._proc
            for line in proc.stdout:  # type: ignore[union-attr]
                if line.startswith(("out_time_us=", "out_time_ms=")):
                    try:
                        sec = int(line.split("=", 1)[1]) / 1_000_000
                    except ValueError:
                        continue
                    frac = min(1.0, max(0.0, sec / max(expected, 0.001)))
                    self._progress(min(0.99, (self._acc + weight * frac) / self._W), label)
            rc = proc.wait()
        if self._cancel.is_set():
            raise RenderCancelled()
        if rc != 0:
            raise FFmpegFailed(explain(errpath.read_text(encoding="utf-8", errors="replace")))
        self._acc += weight

    def _validate_output(self, path: str, total: float, expect_audio: bool):
        if not Path(path).is_file() or Path(path).stat().st_size == 0:
            raise RenderError("Export failed: the output file is empty.")
        info = probe(path, self.ffmpeg)
        if not info.has_video:
            raise RenderError("Export check failed: no video stream in output.")
        if expect_audio and not info.has_audio:
            raise RenderError("Export check failed: audio is missing from output.")
        if info.duration is None or abs(info.duration - total) > 0.75:
            raise RenderError(f"Export check failed: expected about {total:.1f}s but got "
                              f"{info.duration}.")
