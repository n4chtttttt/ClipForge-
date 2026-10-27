from __future__ import annotations
from pathlib import Path

from ..models import Segment, Word


class WhisperTranscriber:
    """Local speech-to-text using faster-whisper (free, runs on your GPU or CPU)."""

    def __init__(self, model_size: str = "small", device: str = "auto", compute_type: str = "int8",
                 language: str = "auto"):
        self.model_size, self.device, self.compute_type = model_size, device, compute_type
        self.language = language
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # imported lazily so tests don't need it
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    def _run(self, media_path: Path, on_progress=None) -> list[Segment]:
        model = self._load()
        options = {
            "word_timestamps": True,
            "vad_filter": True,
            "beam_size": 5,  # Wider search improves recognition at some extra processing time.
            "condition_on_previous_text": False,
        }
        if self.language in {"en", "tl"}:
            options["language"] = self.language
        elif self.language == "mixed":
            # Requires faster-whisper 1.1+; detect language while decoding segments.
            options["multilingual"] = True

        if self.language in {"auto", "en", "mixed"}:
            # Phrase hints help Whisper resolve this common phonetic confusion.
            options["hotwords"] = "merry-go-round"
        raw_segments, info = model.transcribe(str(media_path), **options)
        total = max(float(getattr(info, "duration", 0) or 0), 1.0)
        out: list[Segment] = []
        # raw_segments is a generator: the real work (and any CUDA error)
        # happens while looping, so this loop must run inside the try block
        # in transcribe() below.
        for s in raw_segments:
            words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or [])]
            out.append(Segment(s.start, s.end, s.text.strip(), words))
            if on_progress:
                on_progress(min(1.0, s.end / total))
        return out

    def transcribe(self, media_path: Path, on_progress=None) -> list[Segment]:
        try:
            return self._run(media_path, on_progress)
        except RuntimeError as e:
            # Example: "Library cublas64_12.dll is not found or cannot be loaded"
            if self.device == "cpu":
                raise  # already on CPU, so this is a different problem
            print(f"GPU failed ({e}). Falling back to CPU...")
            self.device = "cpu"   # remember, so later videos skip the GPU attempt
            self._model = None    # drop the broken GPU model so _load() rebuilds it on CPU
            return self._run(media_path, on_progress)
