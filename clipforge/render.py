from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

from .captions import build_ass
from .models import Moment, Segment


def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None


def has_nvenc() -> bool:
    if not ffmpeg_ok():
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return "h264_nvenc" in out


def render_short(
    source: Path, moment: Moment, segments: list[Segment], out_path: Path, *, use_nvenc: bool = True
) -> Path:
    """Cut the moment, make it 1080x1920 (blurred background + centered video), burn in captions."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ass_name = out_path.stem + ".ass"
    (out_path.parent / ass_name).write_text(
        build_ass(segments, moment.start, moment.end), encoding="utf-8"
    )
    vf = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
        "[b]scale=1080:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles={ass_name}[v]"
    )
    encoder = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23"] if (use_nvenc and has_nvenc()) \
        else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{moment.start:.2f}", "-t", f"{moment.duration:.2f}", "-i", str(source.resolve()),
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
        *encoder, "-af", f"afade=t=out:st={max(0.0, moment.duration - 0.2):.2f}:d=0.2",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path.name,
    ]
    # Run inside the output folder so the subtitle filename needs no Windows path escaping.
    subprocess.run(cmd, cwd=out_path.parent, check=True)
    return out_path
