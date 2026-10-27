"""A free, no-AI-model scorer based on transcript patterns.

It is intentionally simple so you can see WHY a moment was picked. It is the
baseline: a smarter scorer (a local LLM, or a cloud API) can be added later and
compared against this one.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..models import Moment, Segment

HOOK_WORDS = {
    "secret", "mistake", "never", "always", "nobody", "truth", "why", "stop", "biggest",
    "worst", "best", "actually", "crazy", "shocking", "story", "learned", "problem",
    "changed", "wrong", "reason", "everyone", "money", "free", "hack",
}
FILLERS = {"um", "uh", "like", "basically", "literally", "yeah", "okay"}
DANGLING_WORDS = {
    # English
    "and", "but", "or", "so", "because", "although", "though", "if", "when", "while",
    "unless", "the", "a", "an", "to", "with", "for", "of", "in", "on", "at", "by", "from",
    "which", "who",
    # Tagalog / Filipino
    "at", "pero", "kasi", "dahil", "kaya", "kung", "kapag", "ang", "ng", "sa", "yung", "tapos", "para",
}
LEADING_FILLERS = {"um", "uh", "erm", "hmm", "ah", "eh"}
# Short reactions and connective words often signal that a complete sentence
# is still part of a larger thought or payoff.
END_CONTINUATION_STARTERS = {
    "and", "but", "so", "because", "then", "also", "though", "although",
    "wow", "yeah", "yes", "no", "oh", "ah", "exactly", "everything",
    "this", "that", "we", "they", "it", "he", "she", "i", "i'm", "im",
}


@dataclass(frozen=True)
class _TimedToken:
    start: float
    end: float
    text: str

    @property
    def normalized(self) -> str:
        words = _words(self.text)
        return words[-1] if words else ""


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
    @staticmethod
    def _tokens(segments: list[Segment]) -> list[_TimedToken]:
        tokens: list[_TimedToken] = []
        for segment in segments:
            if segment.words:
                tokens.extend(
                    _TimedToken(word.start, word.end, word.text.strip())
                    for word in segment.words
                    if word.text.strip() and word.end > word.start
                )
            elif segment.text.strip() and segment.end > segment.start:
                # Keep the whole segment as one timing unit when word alignment is
                # unavailable; do not invent word timestamps by splitting it.
                tokens.append(_TimedToken(segment.start, segment.end, segment.text.strip()))
        return sorted(tokens, key=lambda token: (token.start, token.end))

    @staticmethod
    def _pause_threshold(tokens: list[_TimedToken]) -> float:
        gaps = sorted(
            max(0.0, tokens[index + 1].start - tokens[index].end)
            for index in range(len(tokens) - 1)
            if tokens[index + 1].start - tokens[index].end > 0
        )
        if not gaps:
            return 0.45
        median = gaps[len(gaps) // 2]
        p85 = gaps[min(len(gaps) - 1, math.ceil(len(gaps) * 0.85) - 1)]
        return max(0.35, p85, median * 2.5)

    @staticmethod
    def _is_sentence_end(token: _TimedToken) -> bool:
        return bool(re.search(r"[.!?…][\"')\]]*$", token.text.strip()))

    @staticmethod
    def _continues_immediately(
        token: _TimedToken, next_token: _TimedToken | None
    ) -> bool:
        if next_token is None or not HeuristicScorer._is_sentence_end(token):
            return False
        gap = max(0.0, next_token.start - token.end)
        return gap <= 1.5 and next_token.normalized in END_CONTINUATION_STARTERS

    @staticmethod
    def _boundary_reason(
        token: _TimedToken,
        pause: float,
        threshold: float,
        next_token: _TimedToken | None = None,
    ) -> tuple[float, str]:
        score = 0.0
        reasons: list[str] = []
        sentence_end = HeuristicScorer._is_sentence_end(token)
        if sentence_end:
            score += 3.0
            reasons.append("complete sentence")
        if pause >= threshold:
            score += min(1.5, 0.8 + (pause - threshold))
            reasons.append(f"{pause:.1f}s pause")
        elif not sentence_end:
            score -= 3.0
            reasons.append("cuts mid-sentence")

        if token.normalized in DANGLING_WORDS:
            score -= 4.0
            reasons.append("ends on a dangling word")

        if HeuristicScorer._continues_immediately(token, next_token):
            score -= 4.5
            reasons.append("speech continues immediately")

        return score, ", ".join(reasons) or "natural speech boundary"

    def find_moments(
        self,
        segments: list[Segment],
        *,
        min_seconds: float,
        max_seconds: float | None = None,
        top_n: int,
    ) -> list[Moment]:
        if min_seconds <= 0 or top_n <= 0:
            return []

        hard_cap = max_seconds if max_seconds is not None else min(min_seconds * 1.6, 90.0)
        if hard_cap < min_seconds:
            raise ValueError("Maximum clip duration must be at least the minimum duration.")

        tokens = self._tokens(segments)
        if not tokens:
            return []

        pause_threshold = self._pause_threshold(tokens)
        pauses = [
            max(0.0, tokens[index + 1].start - token.end)
            if index + 1 < len(tokens)
            else 0.0
            for index, token in enumerate(tokens)
        ]

        # Begin at the start of the transcript, or after a clear pause/sentence end.
        start_indexes = [
            index for index, token in enumerate(tokens)
            if index == 0
            or self._is_sentence_end(tokens[index - 1])
            or pauses[index - 1] >= pause_threshold
        ]

        candidates: list[Moment] = []
        for start_index in start_indexes:
            start_token = tokens[start_index]
            start = start_token.start
            first_word = start_token.normalized
            start_score = -1.5 if first_word in LEADING_FILLERS else 0.0
            start_candidates: list[tuple[Moment, bool, bool]] = []

            for end_index in range(start_index, len(tokens)):
                end_token = tokens[end_index]
                end = end_token.end
                dur = end - start
                if dur > hard_cap:
                    break
                if dur < min_seconds:
                    continue

                text = " ".join(token.text for token in tokens[start_index : end_index + 1])
                content_score, content_reason = score_text(text, dur)
                if content_reason == "too little speech":
                    continue

                next_token = tokens[end_index + 1] if end_index + 1 < len(tokens) else None
                continues_immediately = self._continues_immediately(end_token, next_token)
                boundary_score, boundary_reason = self._boundary_reason(
                    end_token, pauses[end_index], pause_threshold, next_token
                )
                # A modest preference for concise clips avoids always stretching
                # candidates to the hard cap while leaving room for a good payoff.
                length_penalty = 0.04 * max(0.0, dur - min_seconds)
                score = content_score + start_score + boundary_score - length_penalty
                if score <= 0:
                    continue

                title = text[:160].strip()
                reason = f"{content_reason}; cut: {boundary_reason}"
                if start_score < 0:
                    reason += "; starts with a filler"
                moment = Moment(max(0.0, start - 0.08), end + 0.4, score, reason, title)
                natural_ending = (
                    self._is_sentence_end(end_token) or pauses[end_index] >= pause_threshold
                )
                start_candidates.append((moment, natural_ending, continues_immediately))

            # Prefer a complete sentence or a natural pause that is not followed
            # immediately by another part of the same thought or reaction.
            clean_natural = [
                moment
                for moment, natural, continues in start_candidates
                if natural and not continues
            ]
            natural_candidates = clean_natural or [
                moment for moment, natural, _ in start_candidates if natural
            ]
            if natural_candidates:
                candidates.extend(natural_candidates)
            elif start_candidates:
                candidates.append(max(start_candidates, key=lambda item: item[0].score)[0])

        candidates.sort(key=lambda m: m.score, reverse=True)
        chosen: list[Moment] = []
        for c in candidates:
            if all(c.end <= m.start or c.start >= m.end for m in chosen):
                chosen.append(c)
            if len(chosen) >= top_n:
                break
        return sorted(chosen, key=lambda m: m.start)
