import tempfile
import unittest
from pathlib import Path

from clipforge.captions import build_ass
from clipforge.config import Settings
from clipforge.models import Segment, Word
from clipforge.pipeline import run_pipeline
from clipforge.providers.heuristic_scorer import HeuristicScorer
from clipforge.jobs import JobStore
from unittest.mock import patch


def make_segments():
    boring = "so um yeah we were just sitting there and uh talking about the weather today you know"
    hooky = "Here is the biggest mistake nobody tells you about! Why do 90 percent of people fail? The truth is simple."
    segs, t = [], 0.0
    for text in [boring] * 4 + [hooky] * 4 + [boring] * 4:
        words = text.split()
        step = 6.0 / len(words)
        segs.append(Segment(t, t + 6.0, text, [Word(t + k * step, t + (k + 1) * step, w) for k, w in enumerate(words)]))
        t += 6.0
    return segs


class FakeTranscriber:
    def transcribe(self, media_path):
        return make_segments()


class BrokenTranscriber:
    def transcribe(self, media_path):
        raise RuntimeError("transcription failed")


class Tests(unittest.TestCase):
    def test_scorer_prefers_hooky_section(self):
        moments = HeuristicScorer().find_moments(make_segments(), min_seconds=20, max_seconds=30, top_n=1)
        self.assertEqual(len(moments), 1)
        self.assertGreaterEqual(moments[0].start, 20.0)   # hooky block starts at 24s
        self.assertLessEqual(moments[0].end, 54.0)

    def test_captions_are_relative_to_clip(self):
        ass = build_ass(make_segments(), 24.0, 48.0)
        self.assertIn("Dialogue: 0,0:00:00.00", ass)

    def test_pipeline_end_to_end_without_rendering(self):
        with tempfile.TemporaryDirectory() as d:
            settings = Settings(data_dir=Path(d), top_n=2)
            rendered = []
            result = run_pipeline(
                Path("fake.mp4"), settings, FakeTranscriber(), HeuristicScorer(),
                renderer=lambda *a, **k: rendered.append(a[1]) or a[3], log=lambda m: None,
            )
            self.assertTrue(result["moments"])
            self.assertEqual(len(rendered), len(result["moments"]))
            self.assertTrue((settings.jobs_dir / result["job_id"] / "result.json").exists())

    def test_pipeline_closes_database_and_records_failure(self):
        with tempfile.TemporaryDirectory() as d:
            settings = Settings(data_dir=Path(d))
            original_close = JobStore.close
            with patch.object(JobStore, "close", autospec=True, side_effect=original_close) as close:
                with self.assertRaisesRegex(RuntimeError, "transcription failed"):
                    run_pipeline(Path("broken.mp4"), settings, BrokenTranscriber(), HeuristicScorer())
                close.assert_called_once()
            with JobStore(settings.db_path) as jobs:
                failed = jobs.list()[0]
                self.assertEqual(failed["status"], "failed")
                self.assertIn("transcription failed", failed["error"])


if __name__ == "__main__":
    unittest.main()
