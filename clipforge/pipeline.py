from __future__ import annotations
import inspect
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .config import Settings
from .jobs import JobStore
from .models import segments_from_dict, segments_to_dict
from .providers.base import MomentScorer, Transcriber
from .render import render_short


def run_pipeline(
    source: Path,
    settings: Settings,
    transcriber: Transcriber,
    scorer: MomentScorer,
    *,
    render: bool = True,
    renderer: Callable = render_short,
    log: Callable[[str], None] = print,
    job_id: str | None = None,
) -> dict:
    jobs = JobStore(settings.db_path)
    job_id = job_id or jobs.create(str(source))
    job_dir = settings.jobs_dir / job_id
    def emit(message: str, *, stage: str | None = None, progress: int | None = None) -> None:
        log(message)
        jobs.update(job_id, stage=stage, progress=progress, message=message)
    try:
        jobs.start(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        emit(f"[1/3] Transcribing {source.name} ...", stage="Transcribing", progress=5)
        started = time.time()
        last = {"pct": -1}

        def on_transcribe_progress(fraction: float) -> None:
            pct = int(fraction * 100)
            if pct == last["pct"]:
                return
            last["pct"] = pct
            note = f"   transcribing {pct}% ({int(time.time() - started)}s elapsed)" if pct % 10 == 0 else None
            jobs.update(job_id, progress=5 + int(40 * fraction), message=note)

        if "on_progress" in inspect.signature(transcriber.transcribe).parameters:
            segments = transcriber.transcribe(source, on_progress=on_transcribe_progress)
        else:
            segments = transcriber.transcribe(source)
        (job_dir / "transcript.json").write_text(json.dumps(segments_to_dict(segments)), encoding="utf-8")

        emit("[2/3] Finding engaging moments ...", stage="Finding moments", progress=45)
        moments = scorer.find_moments(
            segments,
            min_seconds=settings.min_clip_seconds,
            max_seconds=settings.max_clip_seconds,
            top_n=settings.top_n,
        )
        for i, m in enumerate(moments, 1):
            emit(f"   #{i} {m.start:6.1f}-{m.end:6.1f}s  score {m.score:4.1f}  ({m.reason})")

        clips: list[str] = []
        if render:
            emit("[3/3] Rendering Shorts ...", stage="Rendering clips", progress=55)
            for i, m in enumerate(moments, 1):
                out = job_dir / f"clip_{i:02d}.mp4"
                renderer(source, m, segments, out, use_nvenc=settings.use_nvenc)
                clips.append(str(out))
                emit(f"   wrote {out}", progress=55 + int(40 * i / max(1, len(moments))))

        result = {"job_id": job_id, "moments": [asdict(m) for m in moments], "clips": clips}
        (job_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        jobs.finish(job_id, result)
        return result
    except Exception as exc:
        jobs.fail(job_id, repr(exc))
        raise
    finally:
        jobs.close()
