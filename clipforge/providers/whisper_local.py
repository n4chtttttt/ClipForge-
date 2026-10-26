from __future__ import annotations
from pathlib import Path

from ..models import Segment, Word


class WhisperTranscriber:
    """Local speech-to-text using faster-whisper (free, runs on your GPU or CPU)."""

    def __init__(self, model_size: str = "small", device: str = "auto", compute_type: str = "int8"):
        self.model_size, self.device, self.compute_type = model_size, device, compute_type
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # imported lazily so tests don't need it
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    def transcribe(self, media_path: Path) -> list[Segment]:
        model = self._load()
        raw_segments, _info = model.transcribe(
            str(media_path), word_timestamps=True, vad_filter=True
        )
        out: list[Segment] = []
        for s in raw_segments:
            words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or [])]
            out.append(Segment(s.start, s.end, s.text.strip(), words))
        return out
