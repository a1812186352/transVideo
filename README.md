# transVideo

> **Video Structure Decomposition → Migratable Script → Personalized Generation**

transVideo is a full-stack video analysis and re-generation platform. Upload a video, let the local pipeline analyze its structure (scenes, audio, text, visual features), edit the result in a Vue 3 timeline workbench, and export a new MP4 — all **offline**, no external API keys required.

![Tech Stack](https://img.shields.io/badge/backend-FastAPI-009688?style=flat-square)
![Tech Stack](https://img.shields.io/badge/frontend-Vue_3%20%2F%20Pinia-4FC08D?style=flat-square)
![Tech Stack](https://img.shields.io/badge/analysis-OpenCV%20%2F%20Whisper%20%2F%20Librosa-2196F3?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

---

## Architecture

```
Input Video
  │
  ├─ [Signal Layer · Local]
  │   OpenCV Frame Diff + PySceneDetect Scene Boundaries
  │   Whisper (small) Transcription + Librosa Beat/Energy/Silence
  │   Tesseract OCR Text Extraction + OpenCV Frame Extraction
  │   → Outputs: diff matrix, scene boundaries, speech timeline, text regions
  │
  ├─ [Filter Layer · Local]
  │   Adaptive Sampling: frame diff exceeds threshold → keyframe capture
  │   IoU fusion with scene boundaries → final keyframe list
  │   → Outputs: filtered keyframes with timestamps and signal context
  │
  ├─ [Understanding Layer · Local]
  │   Rule Engine: 5-type sliding-window classifier
  │   (Opening / Highlight / Transition / Effect / Closing)
  │   + Visual Features (face/optical flow/saturation/edge density)
  │   + OCR signals + speech duration inference
  │   → Outputs: structured module tree with scene labels, emotion, BGM type
  │
  ├─ [Orchestration Layer · User Edits]
  │   Vue 3 dual-view workbench → drag & drop modules on timeline
  │   → Outputs: Migratable Script (JSON)
  │
  └─ [Generation Layer · Local]
     HyperFrames HTML rendering → FFmpeg transcode/subtitle burn/concat
     → Outputs: MP4
```

---

## Quick Start

### Prerequisites

| Component | Required? | Notes |
|-----------|-----------|-------|
| Python 3.11+ | ✅ Required | Core runtime |
| Node.js 18+ | ✅ Required | Frontend build |
| FFmpeg | ✅ Required | Video/Audio processing |
| Tesseract OCR | ⬜ Optional | Text detection (skip if absent) |

### Install Dependencies

```bash
# Minimal install (frame diff + scene detection + structure inference)
pip install opencv-python scenedetect

# Full local install (speech + audio + OCR)
pip install opencv-python scenedetect openai-whisper librosa pytesseract

# Backend API server
pip install fastapi uvicorn httpx aiofiles

# Frontend
cd frontend && npm install
```

### Run

```bash
# Terminal 1 — Start backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Start frontend dev server
cd frontend && npm run dev
```

Open **http://localhost:5173** in your browser. Upload a video → click "Analyze" → inspect results → edit the script on the timeline → export MP4.

### API Settings

Configure the backend URL in the ⚙ Settings panel (default: `http://localhost:8000`).

---

## Module Overview

| Module | Layer | Responsibility | Dependencies |
|--------|-------|---------------|--------------|
| `understanding/signal/` | Signal (local) | Frame diff, scene detection, speech transcription, audio analysis, OCR, frame extraction | OpenCV / PySceneDetect / Whisper / Librosa / Tesseract |
| `understanding/filter/` | Filter (local) | Adaptive keyframe sampling (percentile threshold, density, boundary forcing) | Pure Python |
| `understanding/understand/` | Understanding (local) | Rule-engine 5-type sliding-window structure inference + visual features (face/optical flow/YOLO) | OpenCV (optional ultralytics) |
| `backend/` | Application | FastAPI server, pipeline orchestration, SSE real-time push, JobStore persistence | FastAPI + uvicorn |
| `frontend/` | Application | Vue 3 dual-view workbench, drag & drop timeline, inspector panel, monitor panel | Vite + Vue 3 + Pinia |
| `generation/` | Generation | HyperFrames HTML template rendering + FFmpeg fallback dual path | FFmpeg |
| `processing/` | Generation | FFmpeg transcoding, subtitle burn-in, concatenation, crossfade (xfade) | FFmpeg |

### Optional Dependencies

| Component | Package | Size | Required? |
|-----------|---------|------|-----------|
| Frame diff + extraction | opencv-python | ~90 MB | ✅ Yes |
| Scene detection | scenedetect | ~1 MB | ✅ Yes |
| Speech transcription | openai-whisper + torch | ~2 GB | ⬜ Optional |
| Audio analysis | librosa | ~80 MB | ⬜ Optional |
| Audio extraction | ffmpeg | ~100 MB | ⬜ Optional |
| OCR | pytesseract + Tesseract | ~50 MB | ⬜ Optional |
| Visual features + YOLO | ultralytics | ~200 MB | ⬜ Optional |

**Minimum usable config**: opencv-python + scenedetect (~90 MB) — enables frame diff, scene detection, and structure inference.

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Script format | Custom JSON Schema (Pydantic + jsonschema) | Dual-source validation serving both API and Python layers |
| Structure inference | 5-type sliding-window rule engine | Zero API dependency, fully local |
| Render engine | HyperFrames HTML → FFmpeg fallback | Reduces hard dependency on external CLI |
| Frontend framework | Vue 3 + Pinia + TypeScript | Lightweight, reactive, multi-track timeline ready |
| OCR engine | Tesseract (offline) | Lightweight, no GPU needed |
| Visual features | OpenCV Haar + optical flow + YOLO (optional) | Zero-model startup, graceful YOLO degradation |
| Task persistence | SQLite (JobStore) | Zero dependency, survives process restart |
| Progress push | SSE (Server-Sent Events) | Real-time pipeline progress to frontend monitor |
| Component loading | Full lazy loading + independent degradation | Any single component missing won't block the rest |
| Audio processing | ffmpeg extract → librosa analyze | Avoids librosa hanging on direct video input |

---

## Development

### Code Style

```bash
# Python — ruff
ruff check backend/ understanding/ generation/ processing/

# TypeScript/Vue — biome
cd frontend && npx biome check src/
```

See [CODE_STYLE.md](docs/CODE_STYLE.md) for full rules.

### Project Structure

```
transVideo/
├── backend/           # FastAPI server (routers, models, store)
├── frontend/          # Vue 3 + Vite SPA
│   └── src/
│       ├── components/   # TimelineBar, PreviewPanel, etc.
│       ├── stores/       # Pinia (project, workbench)
│       ├── types/        # TypeScript types
│       └── views/        # Workbench.vue
├── understanding/     # Video analysis pipeline
│   ├── signal/           # Frame diff, scene detect, OCR, audio
│   ├── filter/           # Adaptive keyframe sampling
│   └── understand/       # Structure inference
├── generation/        # HyperFrames HTML + FFmpeg render
├── processing/        # FFmpeg transcoding, subtitles, concat
├── docs/              # Documentation
└── tests/             # Test suite
```

---

## License

MIT
