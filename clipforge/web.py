"""Local-first ClipForge web interface. No external services or runtime assets."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath

from .config import Settings
from .jobs import JobStore
from .pipeline import run_pipeline
from .providers.heuristic_scorer import HeuristicScorer
from .providers.whisper_local import WhisperTranscriber
from .render import ffmpeg_ok

VIDEO_TYPES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
UPLOAD_ID = re.compile(r"^[a-f0-9]{32}$")
JOB_ID = re.compile(r"^[a-f0-9]{8}$")
CLIP_NAME = re.compile(r"^clip_\d{2}\.mp4$")


def _safe_name(raw: str) -> str:
    name = PureWindowsPath(raw).name
    name = Path(name).name
    name = re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("._")
    return name[:120] or "source-video.mp4"


def create_server(data_dir: Path, *, host="127.0.0.1", port=8765, transcriber_factory=None,
                  scorer_factory=HeuristicScorer, renderer=None) -> ThreadingHTTPServer:
    data_dir = data_dir.resolve()
    upload_dir = data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    template_dir = Path(__file__).parent / "web_static"
    transcriber_factory = transcriber_factory or (lambda opts: WhisperTranscriber(
        opts["model"], opts["device"], "int8"))

    class Handler(BaseHTTPRequestHandler):
        server_version = "ClipForgeLocal/1.0"

        def log_message(self, fmt, *args):
            print(f"[web] {self.address_string()} {fmt % args}")

        def _json(self, value, status=200):
            payload = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _body_json(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64_000:
                raise ValueError("Invalid request body")
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                return self._file(template_dir / "index.html")
            if path in ("/app.js", "/styles.css", "/logo.png"):
                return self._file(template_dir / path.lstrip("/"))
            if path == "/api/jobs":
                with JobStore(data_dir / "clipforge.db") as jobs:
                    return self._json({"jobs": jobs.list()})
            match = re.fullmatch(r"/api/jobs/([a-f0-9]{8})", path)
            if match:
                with JobStore(data_dir / "clipforge.db") as jobs:
                    job = jobs.get(match.group(1))
                return self._json({"job": job} if job else {"error": "Job not found"}, 200 if job else 404)
            match = re.fullmatch(r"/media/([a-f0-9]{8})/(clip_\d{2}\.mp4)", path)
            if match and JOB_ID.fullmatch(match.group(1)) and CLIP_NAME.fullmatch(match.group(2)):
                target = (data_dir / "jobs" / match.group(1) / match.group(2)).resolve()
                if not target.is_relative_to((data_dir / "jobs").resolve()) or not target.is_file():
                    return self._json({"error": "Clip not found"}, 404)
                return self._media(target, download=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("download") == ["1"])
            return self._json({"error": "Not found"}, 404)

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/upload":
                return self._upload()
            if path == "/api/jobs":
                return self._start_job()
            return self._json({"error": "Not found"}, 404)

        def _upload(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0:
                return self._json({"error": "Choose a non-empty video file."}, 400)
            name = _safe_name(urllib.parse.unquote(self.headers.get("X-File-Name", "video.mp4")))
            suffix = Path(name).suffix.lower()
            if suffix not in VIDEO_TYPES:
                return self._json({"error": "Use an MP4, MOV, MKV, AVI, WebM, or M4V video."}, 415)
            upload_id = uuid.uuid4().hex
            destination = upload_dir / f"{upload_id}_{name}"
            remaining = length
            try:
                with destination.open("wb") as output:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise OSError("Upload ended before all bytes arrived")
                        output.write(chunk)
                        remaining -= len(chunk)
            except Exception:
                destination.unlink(missing_ok=True)
                return self._json({"error": "The upload did not finish. Try again."}, 400)
            return self._json({"upload_id": upload_id, "filename": name, "bytes": length}, 201)

        def _start_job(self):
            try:
                body = self._body_json()
                if not isinstance(body, dict):
                    raise ValueError("Invalid job request.")
                upload_id = str(body.get("upload_id", ""))
                if not UPLOAD_ID.fullmatch(upload_id):
                    raise ValueError("Choose or upload a source video first.")
                options = body.get("options", {})
                if not isinstance(options, dict):
                    raise ValueError("Job options must be an object.")
                top_n = int(options.get("top_n", 5))
                minimum = float(options.get("min_clip_seconds", 20))
                maximum = float(options.get("max_clip_seconds", 55))
                model = str(options.get("whisper_model", "small"))
                device = str(options.get("whisper_device", "auto"))
                if not 1 <= top_n <= 10 or not 5 <= minimum < maximum <= 180:
                    raise ValueError("Use 1–10 clips and a valid duration between 5 and 180 seconds.")
                if model not in {"tiny", "base", "small"} or device not in {"auto", "cpu", "cuda"}:
                    raise ValueError("Choose a supported transcription model and device.")
                source = next((p for p in upload_dir.glob(upload_id + "_*") if p.suffix.lower() in VIDEO_TYPES), None)
                if source is None or not source.resolve().is_relative_to(upload_dir.resolve()):
                    raise ValueError("That uploaded source is no longer available. Upload it again.")
                if not ffmpeg_ok():
                    return self._json({"error": "FFmpeg was not found. Install FFmpeg, reopen the terminal, and restart ClipForge."}, 503)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 400)

            settings = Settings(data_dir=data_dir, top_n=top_n, min_clip_seconds=minimum,
                                max_clip_seconds=maximum, whisper_model=model,
                                whisper_device=device)
            with JobStore(settings.db_path) as jobs:
                job_id = jobs.create(str(source))
            self._json({"job_id": job_id}, 202)

            def work():
                try:
                    run_pipeline(source, settings, transcriber_factory({"model": model, "device": device}),
                                 scorer_factory(), render=True, job_id=job_id,
                                 **({"renderer": renderer} if renderer else {}), log=lambda _message: None)
                except Exception as exc:
                    print(f"[job {job_id}] {exc!r}")
                    with JobStore(settings.db_path) as jobs:
                        jobs.fail(job_id, repr(exc))

            threading.Thread(target=work, name=f"clipforge-{job_id}", daemon=True).start()

        def _file(self, path: Path):
            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _media(self, path: Path, *, download=False):
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match:
                    self.send_error(416)
                    return
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                elif right:
                    start = max(0, size - int(right))
                if start >= size or end < start:
                    self.send_error(416)
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Disposition", f'{"attachment" if download else "inline"}; filename="{path.name}"')
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    return ThreadingHTTPServer((host, port), Handler)


def main():
    port = int(os.environ.get("CLIPFORGE_PORT", "8765"))
    server = create_server(Path("data"), port=port)
    print(f"ClipForge is ready at http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ClipForge…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
