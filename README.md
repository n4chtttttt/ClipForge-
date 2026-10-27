# ClipForge

A local-first Python application for finding potential YouTube Shorts moments in longer videos, generating clips, and reviewing the results through a local web interface.

> **Status: Work in progress.** The web interface and job-management workflow are implemented. Transcription and rendering still need testing across different Windows environments.

## Features

- Local web interface for selecting and uploading videos or importing a public single-video YouTube link.
- Adjustable minimum clip duration with an automatically calculated maximum.
- Configurable number of candidate clips.
- Speech transcription using Faster-Whisper, with automatic, English, Tagalog, and mixed-language modes.
- Word-timed cut selection that considers pauses, sentence endings, and dangling words.
- Optional local Ollama ranking using transcript meaning, sampled video frames, and relative audio-energy cues. ClipForge falls back to heuristic scoring when the local ranker is unavailable.
- Per-clip keep/reject feedback saved locally and used as examples in later enhanced-ranking runs.
- Background job processing with progress and error logs.
- Clip preview and download functionality.
- Local SQLite database for job history.
- FFmpeg-based video rendering and subtitle generation.

The maximum candidate duration is capped at 1.6 times the selected minimum, up to 90 seconds. This is ClipForge’s selection limit; it is not YouTube’s Shorts length limit.

## Optional local AI ranking with Ollama

Ollama and its model are installed separately and are **not included when you clone this repository**. Enhanced ranking requires Ollama 0.7.0 or later and the `qwen2.5vl:3b` model.

1. Install Ollama from [ollama.com/download](https://ollama.com/download).
2. Open PowerShell and download the model:

   ```powershell
   ollama pull qwen2.5vl:3b
   ```

3. Confirm the model is installed:

   ```powershell
   ollama list
   ```

4. Start ClipForge and select **Enhanced ranking**.

When using the local Ollama service, ranking inputs are processed on your computer. If Ollama or the model is unavailable, ClipForge can fall back to heuristic scoring.

**Check the job log:** if it shows `HTTP Error 400` and `heuristic fallback`, the clips may still finish rendering, but Ollama did not rank them successfully. A completed job does not by itself mean the local AI ranking worked.

The model scores transcripts in their original language, but Tagalog and Taglish accuracy should be checked on your own videos. Scoring does not guarantee that a clip will be engaging or suitable for publication; preview clips before publishing.

## Requirements

- Windows 10 or 11
- Python 3.12
- FFmpeg
- Deno 2.3 or later for YouTube links (local file uploads do not need Deno)
- Internet access for downloading Python packages, Whisper models, and linked videos

## Installation on Windows

### 1. Install Python

Install Python 3.12 from the official Python website:

[python.org/downloads](https://www.python.org/downloads/)

Verify the installation:

```powershell
py -3.12 --version
```

### 2. Install FFmpeg

Open PowerShell and run:

```powershell
winget install Gyan.FFmpeg
```

Restart PowerShell and verify that FFmpeg is available:

```powershell
ffmpeg -version
```

If the command is not recognized, check that FFmpeg is installed and included in your system PATH.

To import YouTube links, install Deno for yt-dlp's YouTube player challenge support:

```powershell
winget install DenoLand.Deno
```

Restart PowerShell after installing it. Local video uploads do not require Deno.

### 3. Clone the repository

Replace the URL below with the actual URL of your GitHub repository:

```powershell
git clone https://github.com/n4chtttttt/ClipForge-.git
cd REPOSITORY
```

### 4. Create a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks environment activation, consult the Python documentation for your system’s activation-policy options.

### 5. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 6. Start the web interface

```powershell
$env:CLIPFORGE_PORT = "8766"
python -m clipforge.web
```

Open this address in your browser:

[http://127.0.0.1:8766](http://127.0.0.1:8766)

Keep the terminal open while using ClipForge. Press `Ctrl+C` in that terminal to stop the server.

## Running tests

With the virtual environment activated, run:

```powershell
python -m unittest discover -s tests -v
```

The current test suite covers the pipeline, clip-caption timing, database cleanup, upload and YouTube-link validation, job processing, and media-serving behavior. Passing tests do not guarantee successful transcription or rendering on every computer.

## Local files

ClipForge stores application data and generated files locally. Depending on the operation, the `data/` directory can contain:

- Uploaded source videos
- Transcripts
- Generated clips and subtitle files
- Job metadata and logs
- The SQLite database

These files should not be committed to Git.

## Known limitations

- Clip selection uses heuristic scoring and may produce clips with weak openings or endings.
- Local AI ranking may fall back to heuristic scoring if Ollama is unavailable or rejects a request.
- GPU transcription may fail if the required CUDA libraries are unavailable.
- CPU transcription is an alternative, but performance depends on the computer and model size.
- Real-world video rendering and playback should be tested on the target computer.
- The application is intended for local use. Do not expose the development server to the public internet without additional security review.

## Responsible use

Only process and publish videos you own or have permission to use. Downloading a video does not automatically grant permission to redistribute it.

## Contributing

This project is under active development. Bug reports, testing feedback, and improvements are welcome.