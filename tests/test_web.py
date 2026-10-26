import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from clipforge.config import Settings
from clipforge.jobs import JobStore
from clipforge.models import Segment, Word
from clipforge.web import create_server


def sample_segments():
    text = "Here is the biggest mistake nobody tells you about! Why do ninety people fail?"
    words = text.split()
    segments = []
    for index in range(8):
        start = index * 4.0
        step = 4.0 / len(words)
        tokens = [Word(start + i * step, start + (i + 1) * step, word) for i, word in enumerate(words)]
        segments.append(Segment(start, start + 4.0, text, tokens))
    return segments


class FakeTranscriber:
    def transcribe(self, path):
        return sample_segments()


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "data"
        self.server = create_server(
            self.data_dir, port=0, transcriber_factory=lambda _opts: FakeTranscriber(),
            renderer=lambda source, moment, segments, output, **kwargs: output.write_bytes(b"real-route-test-mp4-bytes") or output,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_upload_background_job_and_range_serving(self):
        page = urlopen(self.base + "/").read().decode("utf-8")
        self.assertIn("ClipForge", page)
        self.assertIn("/app.js", page)
        upload = urlopen(Request(self.base + "/api/upload", data=b"source-video", method="POST",
                                 headers={"Content-Type": "application/octet-stream", "X-File-Name": "talk.mov"}))
        uploaded = json.loads(upload.read())
        self.assertEqual(uploaded["filename"], "talk.mov")

        payload = json.dumps({"upload_id": uploaded["upload_id"], "options": {
            "top_n": 1, "min_clip_seconds": 20, "max_clip_seconds": 35,
            "whisper_model": "tiny", "whisper_device": "cpu",
        }}).encode()
        with patch("clipforge.web.ffmpeg_ok", return_value=True):
            response = urlopen(Request(self.base + "/api/jobs", data=payload, method="POST",
                                       headers={"Content-Type": "application/json"}))
            job_id = json.loads(response.read())["job_id"]

        deadline = time.time() + 5
        job = None
        while time.time() < deadline:
            job = json.loads(urlopen(self.base + f"/api/jobs/{job_id}").read())["job"]
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.03)
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(job["progress"], 100)
        self.assertTrue(job["logs"])
        self.assertTrue(Path(job["result"]["clips"][0]).is_file())

        clip_path = f"/media/{job_id}/clip_01.mp4"
        request = Request(self.base + clip_path, headers={"Range": "bytes=0-5"})
        with urlopen(request) as clip:
            self.assertEqual(clip.status, 206)
            self.assertEqual(clip.headers["Content-Range"], "bytes 0-5/25")
            self.assertEqual(clip.read(), b"real-r")
        with urlopen(self.base + clip_path + "?download=1") as download:
            self.assertIn("attachment", download.headers["Content-Disposition"])

    def test_upload_rejects_unsupported_and_job_rejects_untrusted_path(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "/api/upload", data=b"data", method="POST",
                            headers={"X-File-Name": "image.png"}))
        self.assertEqual(error.exception.code, 415)
        body = json.dumps({"upload_id": "../../outside", "options": {}}).encode()
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "/api/jobs", data=body, method="POST",
                            headers={"Content-Type": "application/json"}))
        self.assertEqual(error.exception.code, 400)

    def test_job_store_context_closes_sqlite_connection(self):
        store = JobStore(self.data_dir / "lifecycle.db")
        with store as opened:
            job_id = opened.create("source.mp4")
            self.assertEqual(opened.get(job_id)["status"], "queued")
        self.assertIsNone(store.db)

if __name__ == "__main__":
    unittest.main()
