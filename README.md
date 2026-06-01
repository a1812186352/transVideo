# transVideo

视频结构拆解 → 可迁移脚本 → 个性化生成

**核心特性：不依赖外部 API Key 即可完成视频分析。** 信号采集、帧筛选、结构推理全部本地运行。

## 架构

```
输入视频
  │
  ├─[信号层·本地]─────────────────────────────
  │  OpenCV 帧差曲线 + PySceneDetect 场景边界
  │  Whisper (small) 转录 + Librosa 节拍/能量/静音
  │  Tesseract OCR 文字提取 + OpenCV 帧抽取
  │  → 产出：帧差矩阵、场景边界、语音时间轴、文字区域、帧图像
  │
  ├─[筛选层·本地]─────────────────────────────
  │  自适应采样：帧差超过阈值 → 触发帧采集
  │  帧差曲线 + 场景边界 → 交并判定 → 确定采样帧列表
  │  → 产出：筛选后的关键帧序列（附带时间戳和信号上下文）
  │
  ├─[理解层·本地]─────────────────────────────
  │  规则引擎：5 类型滑窗分类器（Opening / Highlight /
  │  Transition / Effect / Closing）
  │  + 视觉特征（人脸/光流/饱和度/边缘密度）
  │  + OCR 信号 + 语音时长推断
  │  → 产出：结构化模块树（带场景标签、情感、BGM 类型）
  │
  ├─[编排层·用户参与]─────────────────────────
  │  前端双通道工作台 → InspectorPanel 参数编辑 → 拖拽排布模块
  │  → 产出：可迁移脚本 (JSON)
  │
  └─[生成层·本地]─────────────────────────────
     HyperFrames HTML 渲染 → FFmpeg 转码/字幕烧录/拼接
     → 产出：MP4
```

## 快速开始

### 安装依赖

```bash
# 最小安装（仅帧差 + 场景检测 + 结构推理）
pip install opencv-python scenedetect

# 完整本地安装（含语音 + 音频 + OCR）
pip install opencv-python scenedetect openai-whisper librosa pytesseract
# 还需安装: FFmpeg, Tesseract OCR (系统级)

# 后端 API
pip install fastapi uvicorn httpx aiofiles

# 前端
cd frontend && npm install
```

### 启动

```powershell
# 启动后端（在项目根目录执行）
uvicorn backend.main:app --reload --port 8000

# 启动前端
cd frontend && npm run dev
```

浏览器打开 http://localhost:5173，上传视频 → 点击"开始分析" → 查看结果 → 编辑脚本 → 导出 MP4。

### API 设置

前端右上角 ⚙ 设置面板可配置后端 API 地址（默认 `http://localhost:8000`）。

## 模块说明

| 模块 | 层级 | 职责 | 依赖 |
|------|------|------|------|
| `understanding/signal/` | 信号层（本地） | 帧差分析、场景检测、语音转录、音频分析、Tesseract OCR、帧提取 | OpenCV / PySceneDetect / Whisper / Librosa / Tesseract |
| `understanding/filter/` | 筛选层（本地） | 自适应采样策略（百分位阈值、区域密度、边界强制捕获） | 纯 Python |
| `understanding/understand/` | 理解层（本地） | 规则引擎 5 类型滑窗结构推理 + 视觉特征提取（人脸/光流/YOLO） | OpenCV（可选 ultralytics） |
| `script/` | 编排层 | JSON Schema 定义、脚本构建/操作/验证（5 项完整性检查） | 纯 Python |
| `backend/` | 应用层 | FastAPI 服务端、管线编排、SSE 实时推送、JobStore 持久化 | FastAPI + uvicorn |
| `frontend/` | 应用层 | Vue 3 双通道工作台、InspectorPanel、拖拽时间轴、Monitor 面板 | Vite + Vue 3 + Pinia |
| `generation/` | 生成层 | HyperFrames HTML 模板渲染、FFmpeg fallback 双路径 | FFmpeg |
| `processing/` | 生成层 | FFmpeg 转码、字幕烧录、拼接、交叉淡化（xfade） | FFmpeg |

## 本地依赖一览

| 组件 | 依赖包 | 大小 | 必需？ |
|------|--------|------|--------|
| 帧差 + 帧提取 | opencv-python | ~90 MB | ✅ 必需 |
| 场景检测 | scenedetect | ~1 MB | ✅ 必需 |
| 语音转写 | openai-whisper + torch | ~2 GB | ⬜ 可选（无则跳过） |
| 音频分析 | librosa | ~80 MB | ⬜ 可选（无则跳过） |
| 音频提取 | ffmpeg | ~100 MB | ⬜ 可选（无则跳过） |
| 文字识别 | pytesseract + Tesseract | ~50 MB | ⬜ 可选（无则跳过） |
| 视觉特征 + YOLO | ultralytics | ~200 MB | ⬜ 可选（无则跳过） |

**最小可用配置**：仅 opencv-python + scenedetect（~90MB），可进行帧差 + 场景检测 + 结构推理。

## 技术决策

| 决策 | 方案 | 理由 |
|------|------|------|
| 脚本格式 | 自研 JSON Schema (Pydantic + jsonschema) | 双源验证，同时服务 API 层和纯 Python 层 |
| 结构推理 | 5 类型滑窗规则引擎 | 零 API 依赖，全本地运行 |
| 渲染引擎 | HyperFrames HTML → FFmpeg fallback | 降低对外部 CLI 的硬依赖 |
| 前端框架 | Vue 3 + Pinia + TypeScript | 轻量响应式，天然适配多轨时间轴 |
| OCR 引擎 | Tesseract（离线） | 轻量离线，无需 GPU |
| 视觉特征 | OpenCV Haar + 光流 + YOLO（可选） | 零模型起步，YOLO 自动降级 |
| 任务持久化 | JSON 文件 (JobStore) | 零依赖，进程重启不丢失 |
| 进度推送 | SSE (Server-Sent Events) | 实时推送分析进度到前端 Monitor |
| 组件加载 | 全懒加载 + 独立降级 | 任一组件缺失不阻断其余分析 |
| 音频处理 | ffmpeg 提取音轨 → librosa 分析 | 兼容视频格式，避免 librosa 直接读视频卡死 |
