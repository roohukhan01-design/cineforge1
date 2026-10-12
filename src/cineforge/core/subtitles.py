"""SRT subtitle generation from scene text."""
from __future__ import annotations

import textwrap


def fmt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def cues_for_scene(text: str, start: float, end: float, max_chars: int):
    """Split text into <=2-line cues timed proportionally to length inside [start, end]."""
    text = " ".join(text.split())
    if not text or end <= start:
        return []
    lines = textwrap.wrap(text, width=max(10, max_chars)) or [text]
    chunks = ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
    weights = [max(1, len(c.replace("\n", " "))) for c in chunks]
    total = sum(weights)
    cues, cur = [], start
    for chunk, w in zip(chunks, weights):
        dur = (end - start) * w / total
        cues.append((cur, cur + dur, chunk))
        cur += dur
    return cues


def build_srt(texts, starts, durations, max_chars=42, offset=0.0, total=None) -> str:
    out, n = [], 1
    for text, st, d in zip(texts, starts, durations):
        a = st + max(0.0, offset)
        b = st + d - 0.05
        if total is not None:
            b = min(b, total)
        for s, e, chunk in cues_for_scene(text, a, b, max_chars):
            out.append(f"{n}\n{fmt_time(s)} --> {fmt_time(e)}\n{chunk}\n")
            n += 1
    return "\n".join(out)
