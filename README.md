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
  ├─[理解层·本地+可选云端]────────────────────
  │  规则引擎：位置检测（片头/片尾）+ 快切检测（蒙太奇）
  │  + 语音时长推断（口播）+ OCR 信号（标题/CTA/Logo）
  │  可选：多模态 LLM 对关键帧做语义描述增强
  │  → 产出：结构化模块树
  │
  ├─[编排层·用户参与]──────────────────────────
  │  前端双通道工作台 → InspectorPanel 参数编辑 → 拖拽排布模块
  │  → 产出：可迁移脚本 (JSON)
  │
  └─[生成层·本地]─────────────────────────────
     HyperFrames 渲染 HTML 视频工程 → FFmpeg 转码/字幕烧录/拼接
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
uvicorn backend.main:app --reload --port 8001

# 启动前端
cd frontend && npm run dev
```

浏览器打开 http://localhost:5173，上传视频 → 点击"开始分析" → 查看结果 → 编辑脚本 → 导出 MP4。

### API 设置

前端右上角 ⚙ 设置面板可配置：
- 后端 API 地址（默认 `http://localhost:8001`）
- LLM API 地址 / Key / 模型名（可选，留空则使用纯本地规则引擎）

## 模块说明

| 模块 | 层级 | 职责 | 依赖 |
|------|------|------|------|
| `understanding/signal/` | 信号层（本地） | 帧差分析、场景检测、语音转录、音频分析、Tesseract OCR、帧提取 | OpenCV / PySceneDetect / Whisper / Librosa / Tesseract |
| `understanding/filter/` | 筛选层（本地） | 自适应采样策略 | 纯 Python |
| `understanding/understand/` | 理解层（本地+可选云端） | 规则引擎结构推理 + 可选多模态 LLM 画面语义 | 纯 Python（LLM 需 API Key） |
| `script/` | 编排层 | JSON Schema 校验、脚本构建/操作/验证 | 纯 Python |
| `backend/` | 应用层 | FastAPI 服务端、管线编排 | FastAPI + uvicorn |
| `frontend/` | 应用层 | Vue 3 双通道工作台、拖拽时间轴编辑器 | Vite + Vue 3 + Pinia |
| `generation/` | 生成层 | HyperFrames 渲染、脚本→HTML 映射 | FFmpeg（fallback） |
| `processing/` | 生成层 | FFmpeg 转码、字幕烧录、拼接、交叉淡化 | FFmpeg |

## 技术决策

| 决策 | 方案 | 理由 |
|------|------|------|
| 脚本格式 | 自研 JSON Schema | 面向"可迁移"，可同时映射到 HTML 和 FFmpeg |
| 结构推理 | 规则引擎优先，LLM 可选 | 零 API 可用，有 API 可增强 |
| 渲染引擎 | HyperFrames HTML → FFmpeg fallback | 降低对外部 CLI 的硬依赖 |
| 前端框架 | Vue 3 + Pinia + TypeScript | 轻量响应式，天然适配多轨时间轴 |
| OCR 引擎 | Tesseract | 用户已安装，轻量离线 |
| 组件加载 | 全懒加载 + 独立降级 | 任一组件缺失不阻断其余分析 |
| 音频处理 | ffmpeg 提取音轨 → librosa 分析 | 兼容视频格式，避免 librosa 直接读视频卡死 |
