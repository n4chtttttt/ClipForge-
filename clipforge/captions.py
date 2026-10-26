from __future__ import annotations
from .models import Segment


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(segments: list[Segment], clip_start: float, clip_end: float, words_per_line: int = 4) -> str:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,76,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,1,2,60,60,420,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines: list[str] = []
    for seg in segments:
        if seg.end < clip_start or seg.start > clip_end:
            continue
        if seg.words:
            tokens = [(w.start, w.end, w.text) for w in seg.words]
        else:  # no word timing: spread the words evenly across the segment
            parts = seg.text.split()
            if not parts:
                continue
            step = (seg.end - seg.start) / len(parts)
            tokens = [(seg.start + k * step, seg.start + (k + 1) * step, p) for k, p in enumerate(parts)]
        for k in range(0, len(tokens), words_per_line):
            chunk = tokens[k : k + words_per_line]
            s = max(chunk[0][0], clip_start) - clip_start
            e = min(chunk[-1][1], clip_end) - clip_start
            if e <= s:
                continue
            text = " ".join(t[2] for t in chunk).replace("{", "(").replace("}", ")")
            lines.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Default,,0,0,0,,{text}")
    return header + "\n".join(lines) + "\n"
