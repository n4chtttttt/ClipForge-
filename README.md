# ClipForge

A local-first Python application for finding potential YouTube Shorts moments in longer videos, generating clips, and reviewing the results through a local web interface.

> **Status: Work in progress.** The web interface and job-management workflow are implemented. Transcription and rendering still need testing across different Windows environments.

## Features

- Local web interface for selecting and uploading videos.
- Adjustable minimum and maximum clip durations.
- Configurable number of candidate clips.
- Speech transcription using Faster-Whisper.
- Heuristic scoring to identify potential engaging moments.
- Background job processing with progress and error logs.
- Clip preview and download functionality.
- Local SQLite database for job history.
- FFmpeg-based video rendering and subtitle generation.

Clip scoring is heuristic-based. It does not guarantee that a clip will be engaging, viral, or suitable for publication. Some generated clips may have awkward beginnings or endings.

## Requirements

- Windows 10 or 11
- Python 3.12
- FFmpeg
- Internet access for downloading Python packages and Whisper models when needed

## Installation on Windows

### 1. Install Python

Install Python 3.12 from the official Python website:

https://www.python.org/downloads/

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

### 3. Clone the repository

Replace `YOUR_GITHUB_USERNAME` with the repository owner's GitHub username.

```powershell
git clone https://github.com/YOUR_GITHUB_USERNAME/clipforge.git
cd clipforge
```

### 4. Create a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks environment activation, consult the Python documentation for your system's activation-policy options.

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

http://127.0.0.1:8766

Keep the terminal open while using ClipForge. Press `Ctrl+C` in that terminal to stop the server.

## Running tests

With the virtual environment activated, run:

```powershell
python -m unittest discover -s tests -v
```

The current test suite covers the pipeline, clip-caption timing, database cleanup, upload validation, job processing, and media-serving behavior. Passing tests do not guarantee successful transcription or rendering on every computer.

## Local files

ClipForge stores application data and generated files locally. Depending on the operation, the `data/` directory can contain:

- Uploaded source videos
- Transcripts
- Generated clips and subtitle files
- Job metadata and logs
- The SQLite database

These files are intentionally excluded from Git.

## Known limitations

- Clip selection uses heuristic scoring and may produce clips with weak openings or endings.
- GPU transcription may fail if the required CUDA libraries are unavailable.
- CPU transcription is an alternative, but performance depends on the computer and model size.
- Real-world video rendering and playback should be tested on the target computer.
- The application is intended for local use. Do not expose the development server to the public internet without additional security review.

## Responsible use

Only process and publish videos you own or have permission to use. Downloading a video does not automatically grant permission to redistribute it.

## Contributing

This project is under active development. Bug reports, testing feedback, and improvements are welcome.