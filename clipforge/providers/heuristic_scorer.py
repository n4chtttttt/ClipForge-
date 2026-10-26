"""A free, no-AI-model scorer based on transcript patterns.

It is intentionally simple so you can see WHY a moment was picked. It is the
baseline: a smarter scorer (a local LLM, or a cloud API) can be added later and
compared against this one.
"""
from __future__ import annotations
import re

from ..models import Moment, Segment

HOOK_WORDS = {
    "secret", "mistake", "never", "always", "nobody", "truth", "why", "stop", "biggest",
    "worst", "best", "actually", "crazy", "shocking", "story", "learned", "problem",
    "changed", "wrong", "reason", "everyone", "money", "free", "hack",
}
FILLERS = {"um", "uh", "like", "basically", "literally", "yeah", "okay"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def score_text(text: str, duration: float) -> tuple[float, str]:
    words = _words(text)
    if duration <= 0 or len(words) < 10:
        return 0.0, "too little speech"
    reasons: list[str] = []
    score = 0.0
    per30 = 30.0 / duration  # count things per 30 seconds so long windows are not favored

    hooks = sum(1 for w in words if w in HOOK_WORDS)
    if hooks:
        score += min(hooks * per30, 12) * 0.5
        reasons.append(f"{hooks} hook words")

    questions = text.count("?")
    if questions:
        score += min(questions * per30, 6) * 0.8
        reasons.append(f"{questions} questions")

    bangs = text.count("!")
    if bangs:
        score += min(bangs * per30, 6) * 0.5
        reasons.append(f"{bangs} exclamations")

    numbers = len(re.findall(r"\d+", text))
    if numbers:
        score += min(numbers * per30, 6) * 0.4
        reasons.append("specific numbers")

    rate = len(words) / duration  # words per second; ~2.0-3.5 feels lively
    if 2.0 <= rate <= 3.5:
        score += 2.0
        reasons.append("lively pace")
    elif rate < 1.2:
        score -= 2.0
        reasons.append("slow pace")

    filler_ratio = sum(1 for w in words if w in FILLERS) / len(words)
    score -= filler_ratio * 10  # smooth penalty so filler-heavy windows always rank lower
    if filler_ratio > 0.08:
        reasons.append("lots of filler")

    first_sentence = re.split(r"[.!?]", text.strip(), maxsplit=1)[0].lower()
    if "?" in text[: len(first_sentence) + 1] or any(w in first_sentence for w in HOOK_WORDS):
        score += 1.5
        reasons.append("strong opening")

    return score, ", ".join(reasons) or "average"


class HeuristicScorer:
    def find_moments(self, segments, *, min_seconds, max_seconds, top_n):
        candidates: list[Moment] = []
        n = len(segments)
        for i in range(n):
            for j in range(i, n):
                start, end = segments[i].start, segments[j].end
                dur = end - start
                if dur > max_seconds:
                    break
                if dur < min_seconds:
                    continue
                text = " ".join(s.text for s in segments[i : j + 1])
                score, reason = score_text(text, dur)
                if score > 0:
                    title = segments[i].text[:60].strip()
                    candidates.append(Moment(max(0.0, start - 0.2), end + 0.2, score, reason, title))

        candidates.sort(key=lambda m: m.score, reverse=True)
        chosen: list[Moment] = []
        for c in candidates:
            if all(c.end <= m.start or c.start >= m.end for m in chosen):
                chosen.append(c)
            if len(chosen) >= top_n:
                break
        return sorted(chosen, key=lambda m: m.start)
