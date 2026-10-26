from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Moment:
    start: float
    end: float
    score: float
    reason: str
    title: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


def segments_to_dict(segments: list[Segment]) -> list[dict]:
    return [asdict(s) for s in segments]


def segments_from_dict(data: list[dict]) -> list[Segment]:
    return [
        Segment(d["start"], d["end"], d["text"], [Word(**w) for w in d.get("words", [])])
        for d in data
    ]
