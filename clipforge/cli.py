from __future__ import annotations
import argparse
from pathlib import Path

from .config import Settings
from .pipeline import run_pipeline
from .providers.heuristic_scorer import HeuristicScorer
from .providers.ollama_scorer import OllamaScorer
from .providers.whisper_local import WhisperTranscriber
from .render import ffmpeg_ok


def main() -> None:
    p = argparse.ArgumentParser(prog="clipforge", description="Turn a video you own into Shorts.")
    p.add_argument("video", type=Path, help="path to a video file you are authorized to use")
    p.add_argument("--top", type=int, default=5, help="how many clips to make")
    p.add_argument("--model", default="small", help="whisper model: tiny/base/small/medium")
    p.add_argument("--device", default="auto", help="auto/cuda/cpu")
    p.add_argument("--scorer", choices=("heuristic", "enhanced"), default="heuristic",
                   help="use the basic scorer or local Ollama text/image ranking")
    p.add_argument("--ranker-model", default="qwen2.5vl:3b", help="local Ollama vision-language model")
    p.add_argument("--language", choices=("auto", "en", "tl", "mixed"), default="auto",
                   help="transcription language: auto, English, Tagalog, or mixed English/Tagalog")
    p.add_argument("--dry-run", action="store_true", help="find moments but do not render")
    args = p.parse_args()

    if not args.video.exists():
        raise SystemExit(f"File not found: {args.video}")
    if not args.dry_run and not ffmpeg_ok():
        raise SystemExit("FFmpeg not found. Install it and make sure `ffmpeg` works in your terminal.")

    settings = Settings(top_n=args.top, whisper_model=args.model, whisper_device=args.device,
                        whisper_language=args.language)
    transcriber = WhisperTranscriber(settings.whisper_model, settings.whisper_device,
                                     settings.whisper_compute, settings.whisper_language)
    scorer = OllamaScorer(model=args.ranker_model) if args.scorer == "enhanced" else HeuristicScorer()
    run_pipeline(args.video, settings, transcriber, scorer, render=not args.dry_run)


if __name__ == "__main__":
    main()
