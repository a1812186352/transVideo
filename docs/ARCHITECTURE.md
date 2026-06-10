# transVideo 架构文档

> 版本 v1.0.0 · 2026-07-14
> 覆盖：数据流、模块职责、目录结构

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                    │
│  Workbench · PreviewPanel · TimelineBar · ScriptPanel    │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / SSE
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend                        │
│  upload · analysis · export · materials · recovery       │
└────────┬────────────┬──────────────┬────────────────────┘
         │            │              │
         ▼            ▼              ▼
   ┌──────────┐ ┌──────────┐ ┌──────────────┐
   │instances/│ │job_store/│ │   output/    │
   │ 视频文件  │ │ SQLite   │ │  渲染产物    │
   └──────────┘ └──────────┘ └──────────────┘
```

## 二、管线数据流

### 2.1 分析管线

```
视频文件 (.mp4/.mov)
    │
    ▼
┌──────────────── SIGNAL LAYER ─────────────────┐
│                                                │
│  FrameExtractor ──► FrameDiffAnalyzer          │
│       │                │                       │
│       ▼                ▼                       │
│  SceneDetect     FrameDiffCurve                │
│       │                │                       │
│       ▼                ▼                       │
│  OCR extract ◄── AdaptiveSampler               │
│  AudioAnalysis                                  │
│  AudioTranscribe (Whisper)                      │
│  VisualFeatures (YOLO + optical flow)           │
│  MotionAnalysis                                 │
│  CompositionGrid                                │
│  VideoClassifier                                │
└───────────────────────┬────────────────────────┘
                        │ signal_data dict
                        ▼
┌──────────────── FILTER LAYER ──────────────────┐
│  AdaptiveSampler (percentile-based keyframes)   │
│  ContentSampler (entropy-gated static frames)   │
└───────────────────────┬────────────────────────┘
                        │ keyframe indices
                        ▼
┌────────────── UNDERSTAND LAYER ────────────────┐
│  StructureInferrer (5-type sliding-window)     │
│  PipelineDetail (per-segment assembly)         │
│  PipelineModules (module tree builder)         │
└───────────────────────┬────────────────────────┘
                        │ module_tree
                        ▼
┌──────────────── SCRIPT LAYER ──────────────────┐
│  ScriptBuilder (from_module_tree)              │
│  ScriptValidator (JSON Schema)                 │
│  ScriptManipulator (add/remove/reorder)        │
└───────────────────────┬────────────────────────┘
                        │ MigratableScript JSON
                        ▼
                  JobStore (analysis.db)
```

### 2.2 渲染管线

```
MigratableScript JSON
    │
    ▼
┌──────────────── EXPORT LAYER ──────────────────┐
│  CompositeEngine                                │
│    ├─ HyperFramesEngine (primary)              │
│    └─ FFmpegEngine (fallback)                  │
│       ├─ _build_base_clips                     │
│       ├─ _apply_text_overlays                  │
│       └─ _apply_subtitles                      │
└───────────────────────┬────────────────────────┘
                        │ output.mp4
                        ▼
                  output/ + JobStore (export.db)
```

## 三、目录结构

```
transVideo/
├── backend/               # FastAPI 应用
│   ├── main.py            # 入口：路由挂载、启动恢复
│   ├── middleware/        # 错误处理、认证
│   ├── models/            # Pydantic 请求/响应模型
│   ├── routers/           # HTTP 路由
│   │   ├── upload.py      # 视频上传 + 缩略图
│   │   ├── analysis.py    # 分析管线触发 + SSE 流
│   │   ├── export.py      # 渲染提交 + SSE 进度
│   │   └── materials.py   # 参考素材 CRUD
│   └── store/             # JobStore (SQLite 持久化)
├── understanding/         # 分析管线
│   ├── signal/            # 信号层
│   │   ├── frame_extractor.py
│   │   ├── frame_diff.py
│   │   ├── scene_detect.py
│   │   ├── audio_transcribe.py
│   │   ├── audio_analysis.py
│   │   ├── visual_features.py
│   │   ├── motion_analysis.py
│   │   ├── composition_grid.py
│   │   ├── video_classifier.py
│   │   ├── ocr_extract.py
│   │   └── vad_detect.py
│   ├── filter/            # 过滤层
│   │   ├── adaptive_sampler.py
│   │   └── content_sampler.py
│   └── understand/        # 理解层
│       └── structure.py
├── script/                # 脚本层
│   ├── builder.py
│   ├── schema.py
│   ├── validator.py
│   └── manipulator.py
├── generation/            # 渲染层
│   ├── render_engine.py   # CompositeEngine + FFmpegEngine
│   ├── composer.py
│   └── renderer.py
├── processing/            # 视频处理工具
│   ├── ffmpeg_utils.py
│   ├── transcoder.py
│   ├── subtitle.py
│   └── concat.py
├── instances/             # 上传视频存储
├── output/                # 渲染输出
├── job_store/             # SQLite 数据
│   ├── analysis.db
│   └── export.db
├── tests/                 # 测试
│   ├── conftest.py
│   ├── _e2e_helpers.py
│   ├── test_e2e.py
│   ├── test_routers.py
│   ├── test_pipeline.py
│   ├── test_script.py
│   ├── test_manipulator.py
│   ├── test_signal_composition_grid.py
│   ├── test_signal_video_classifier.py
│   └── test_signal_frame_diff.py
└── docs/                  # 文档
    ├── CODE_STYLE.md
    ├── ARCHITECTURE.md
    └── API.md
```

## 四、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 分析管线 | 信号→过滤→理解 三层 | 每层可独立缓存/重试，支持 checkpoint 恢复 |
| 脚本格式 | MigratableScript (JSON Schema) | 可在前端编辑后直接提交渲染，不依赖后端版本 |
| 任务持久化 | SQLite (JobStore) | 零外部依赖，WAL 模式支持并发读 |
| 渲染引擎 | CompositeEngine 策略模式 | 自动降级：HyperFrames → FFmpeg |
| SSE 实时更新 | per-video_id queue | 前端实时感知分析/渲染进度 |
