# transVideo

视频结构拆解 → 可迁移脚本 → 个性化生成

**纯本地运行，不依赖任何外部 API Key。** 信号采集、帧筛选、结构推理全部在本地完成。

---

## 项目说明

transVideo 是一个视频叙事结构理解工具：输入任意视频，系统自动拆解其叙事结构，产出可迁移脚本（JSON），用户可在前端拖拽编辑模块后重新生成个性化视频。

五层流水线：

```
输入视频
  │
  ├─[信号层] ─── OpenCV 帧差 + PySceneDetect 场景边界
  │               Whisper 转录 + Librosa 音频分析
  │               Tesseract OCR + OpenCV 帧提取
  │
  ├─[筛选层] ─── 自适应采样（百分位阈值 + 场景边界捕获）
  │
  ├─[理解层] ─── 5 类型滑窗规则引擎（Opening / Highlight /
  │               Transition / Effect / Closing）
  │               + YOLOv8 物体检测（可选）
  │               + 视觉特征（人脸/光流/饱和度/边缘密度）
  │
  ├─[编排层] ─── Vue 3 前端双通道工作台 + 拖拽时间轴
  │
  └─[生成层] ─── HyperFrames HTML 渲染 → FFmpeg 转码/字幕/拼接
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- FFmpeg（可选，用于视频导出）
- Tesseract OCR（可选，用于文字识别）

### 安装

```bash
# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend && npm install
```

### 启动

```powershell
# 启动后端（项目根目录）
uvicorn backend.main:app --reload --port 8001

# 启动前端（另一个终端）
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`，上传视频 → 点击"开始分析" → 查看结果 → 编辑脚本 → 导出 MP4。

> **端口调整**：后端默认 `8001`，前端默认 `5173`。如需更改：
> - 后端：`uvicorn backend.main:app --reload --port <端口>`
> - 前端：修改 `frontend/src/stores/project.ts` 中的 `apiBaseUrl` 默认值，或在前端设置面板中修改
>
> **注意**：Whisper（~2GB）和 YOLOv8n（~6MB）首次运行时会自动下载模型文件，需要联网。最小配置下（仅 opencv + scenedetect）无需下载即可运行帧差分析和结构推理。

## 整体 AI 架构

### 全本地推理管线（无外部依赖）

| 模块 | 模型/算法 | 本地/云端 | 必需 |
|------|-----------|-----------|------|
| 帧差分析 | HSV 直方图卡方距离 | 本地（OpenCV） | ✅ |
| 场景检测 | PySceneDetect ContentDetector | 本地（OpenCV） | ✅ |
| 语音转写 | Whisper small | 本地（~2GB） | ⬜ |
| 音频分析 | Librosa BPM + RMS 能量 | 本地（~80MB） | ⬜ |
| 文字识别 | Tesseract OCR | 本地（~50MB） | ⬜ |
| 物体检测 | YOLOv8n | 本地（~6MB） | ⬜ |
| 视觉特征 | Haar 级联 + Farneback 光流 | 本地（OpenCV） | ✅ |
| 结构推理 | 规则引擎（5 类型滑窗分类器） | 本地（纯 Python） | ✅ |

### 最小可用配置
仅需 `opencv-python` + `scenedetect`（~90MB），即可完成帧差分析、场景检测和结构推理。

## 工具协议

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| POST | `/upload/` | 上传视频文件 |
| GET | `/upload/video/{id}` | 获取视频流（byte-range 支持） |
| GET | `/upload/video/{id}/thumbnail?time=N` | 单帧缩略图（JPEG） |
| GET | `/upload/video/{id}/thumbnails?interval=N` | 批量缩略图列表 |
| POST | `/analyze/{id}` | 启动视频分析 |
| GET | `/analyze/{id}` | 查询分析状态 |
| GET | `/analyze/{id}/stream` | SSE 实时分析进度 |
| POST | `/export/{id}` | 启动视频导出 |
| GET | `/export/{id}` | 查询导出状态 |
| POST | `/materials/upload` | 上传素材（图片/视频） |
| GET | `/materials/list` | 列出素材 |
| DELETE | `/materials/{id}` | 删除素材 |

### 数据流

```
上传 → 分析（信号 → 筛选 → 理解 → 模块树）→ 脚本 JSON
  → 前端编辑 → 导出（HTML → FFmpeg MP4）
```

### 状态码约定

- `200` — 请求成功
- `404` — 视频/资源不存在
- `409` — 冲突（分析/导出正在处理中）
- `413` — 文件超过大小限制
- `422` — 请求参数校验失败

## 安全边界

### 文件隔离
- 上传视频存储在项目 `instances/` 目录，按 UUID 命名防碰撞
- 素材上传限 50MB，仅允许图片和常见视频格式
- 所有文件路径使用 `uuid` 生成，防止路径遍历

### 无外部请求
- 所有分析步骤 **不向外部发送任何 HTTP 请求**
- 不收集任何用户数据、分析日志或视频内容
- 不嵌入任何遥测、分析或广告 SDK

### 依赖安全
- 无运行时网络请求（pip 安装后完全离线可用）
- FFmpeg 子进程通过 `shutil.which()` 查找，不信任 PATH 以外的路径
- 所有子进程设置 `timeout` 防止资源耗尽

### 数据生命期
- 分析中间产物存储在 `job_store/`（SQLite + JSON），进程重启可恢复
- 临时帧缓存存储在 `instances/frames/`，可随时删除
- 日志文件 10MB 轮转，保留 5 个备份

### 风险提示
- Whisper 模型下载约 2GB，YOLOv8n 约 6MB，首次运行需联网下载
- 长视频（>30 分钟）分析耗时可能超过 30 分钟（CPU 推理）
- 前端设置的 API 地址仅用于连接本机后端，不传输至第三方
