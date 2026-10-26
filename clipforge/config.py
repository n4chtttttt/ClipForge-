from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path = Path("data")
    whisper_model: str = "small"      # "base" if your laptop struggles; "small" fits 4 GB VRAM
    whisper_device: str = "auto"      # "auto", "cuda", or "cpu"
    whisper_compute: str = "int8"     # int8 is the safe choice for 4 GB VRAM / 8 GB RAM
    whisper_language: str = "auto"    # auto, en, tl, or mixed
    min_clip_seconds: float = 20.0
    # None lets the scorer choose an internal cap based on the minimum duration.
    max_clip_seconds: float | None = None
    top_n: int = 5
    use_nvenc: bool = True            # GPU video encoding if FFmpeg supports it

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "clipforge.db"
