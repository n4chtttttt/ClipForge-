from __future__ import annotations
import argparse
from pathlib import Path

from .config import Settings
from .pipeline import run_pipeline
from .providers.heuristic_scorer import HeuristicScorer
from .providers.whisper_local import WhisperTranscriber
from .render import ffmpeg_ok


def main() -> None:
    p = argparse.ArgumentParser(prog="clipforge", description="Turn a video you own into Shorts.")
    p.add_argument("video", type=Path, help="path to a video file you are authorized to use")
    p.add_argument("--top", type=int, default=5, help="how many clips to make")
    p.add_argument("--model", default="small", help="whisper model: tiny/base/small")
    p.add_argument("--device", default="auto", help="auto/cuda/cpu")
    p.add_argument("--dry-run", action="store_true", help="find moments but do not render")
    args = p.parse_args()

    if not args.video.exists():
        raise SystemExit(f"File not found: {args.video}")
    if not args.dry_run and not ffmpeg_ok():
        raise SystemExit("FFmpeg not found. Install it and make sure `ffmpeg` works in your terminal.")

    settings = Settings(top_n=args.top, whisper_model=args.model, whisper_device=args.device)
    transcriber = WhisperTranscriber(settings.whisper_model, settings.whisper_device, settings.whisper_compute)
    run_pipeline(args.video, settings, transcriber, HeuristicScorer(), render=not args.dry_run)


if __name__ == "__main__":
    main()
