"""The two seams where cost or hardware could change later.

Today both are implemented locally and free. Later, a cloud implementation
(for example a hosted speech-to-text API or an LLM scorer) can be dropped in
without touching the rest of the pipeline.
"""
from __future__ import annotations
from pathlib import Path
from typing import Protocol

from ..models import Moment, Segment


class Transcriber(Protocol):
    def transcribe(self, media_path: Path) -> list[Segment]: ...


class MomentScorer(Protocol):
    def find_moments(
        self, segments: list[Segment], *, min_seconds: float, max_seconds: float, top_n: int
    ) -> list[Moment]: ...
