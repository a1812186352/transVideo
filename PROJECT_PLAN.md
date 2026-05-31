---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 59ad7eae8b844d65d03e58985f4f272f_480bef325c1011f19299525400d9a7a1
    ReservedCode1: VBS9kOLWEagpr4DZAxWkl9pP1OBxKOhmc/4VHHuXmCTRfF/8ANvVkTn779L5JtZ9eyQDz64d0zl1xZy8r8Jyp8wrjy9laL/gBXEJIR6qyByeB0qofif+z360q73dKGlBnKTY011sWTYUM4krdaPpJqeLvk9W85/QRqj53iqU1SQTIZuAS6xBsGG57BY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 59ad7eae8b844d65d03e58985f4f272f_480bef325c1011f19299525400d9a7a1
    ReservedCode2: VBS9kOLWEagpr4DZAxWkl9pP1OBxKOhmc/4VHHuXmCTRfF/8ANvVkTn779L5JtZ9eyQDz64d0zl1xZy8r8Jyp8wrjy9laL/gBXEJIR6qyByeB0qofif+z360q73dKGlBnKTY011sWTYUM4krdaPpJqeLvk9W85/QRqj53iqU1SQTIZuAS6xBsGG57BY=
---

# transVideo 项目计划

> 版本：v0.5.0 | 更新：2026-05-30 | 状态：端到端可运行，M2 三条关键链路已打通

---

## 一、项目概述

transVideo 是一个**视频结构理解 → 可迁移脚本 → 个性化视频生成**工具。输入任意视频，系统自动拆解其叙事结构，产出可迁移脚本（JSON），用户可在前端拖拽编排模块后重新生成个性化视频。

五层流水线：信号层（本地采集）→ 筛选层（自适应采样）→ 理解层（规则引擎 + 可选 LLM）→ 编排层（用户交互）→ 生成层（HyperFrames + FFmpeg）。

**核心能力：不依赖任何外部 API Key 即可完成视频分析。** 信号采集、帧筛选、结构推理全部本地运行。视觉 LLM 为可选增强。

---

## 二、当前进度总览（2026-05-30 更新）

| 模块 | 完成度 | 状态 |
|------|--------|------|
| `understanding/signal/` | **95%** ✅ | 六大通道全部实现：帧差 / 场景检测 / 语音转录 / 音频分析 / Tesseract OCR / 帧提取；含时间戳、懒加载、错误降级 |
| `understanding/filter/` | **90%** ✅ | 自适应采样含百分位阈值、区域密度、边界强制捕获；新增 `sample_by_count()` 和 `sample_with_context()` |
| `understanding/understand/` | **80%** ✅ | `vision.py` 支持可配置 LLM API，未配置时降级；`structure.py` 的 `infer()` 已实现规则引擎 + 位置/活动 fallback，零 API 可运行 |
| `script/` | **92%** ✅ | Schema + Builder + Manipulator + Validator；新增 `create_empty_script()` / `duplicate_module()` / `shift_all_modules()` / `compact_timeline()`；5 项完整性检查 |
| `backend/` | **80%** ✅ | 路由框架完整（upload/analysis/export）；`_build_module_tree()` 已实现 6 种 segment→Module 映射；OCR 集成；全组件懒加载 + 降级保护 |
| `frontend/` | **80%** ✅ | Vue 3 + Pinia + TypeScript；双通道工作台布局（分析管线 / 生成管线）；中文化 UI；API 设置面板含 Test Connection；InspectorPanel 参数编辑 |
| `generation/` | **75%** ✅ | `composer.py` 完整实现 script→HTML 映射；`renderer.py` HyperFrames CLI + FFmpeg fallback 双路径 |
| `processing/` | **90%** ✅ | FFmpeg transcoder / subtitle burner / concat 完整封装；新增 `ffmpeg_utils.py` / `concat_with_crossfade()` / 超时 + 进度回调 |

### 真实完成情况

- [x] 信号层六通道独立可用（帧差 + 场景检测 + 语音转录 + 音频分析 + Tesseract OCR + 帧提取）
- [x] 自适应采样：帧差阈值 + 场景边界交并判定 + 均匀采样 fallback
- [x] 可迁移脚本 JSON Schema 定义与校验（5 项检查）
- [x] 脚本构建器、操作器（添加/删除/重排/复制/偏移/紧凑化）
- [x] **结构推理规则引擎** — 位置检测（片头/片尾）+ 快切检测（蒙太奇）+ 长语音（口播）+ OCR 规则，零 API 可用
- [x] 管线模块树构建 — 6 种 segment 类型 → Module 映射
- [x] 全组件懒加载 + 降级保护 — 任何组件缺失不影响其余分析
- [x] 前端 Vue 3 双通道工作台 + 拖拽时间轴编辑器
- [x] HyperFrames HTML 模板声明式渲染（`composer.py` 完整）
- [x] FFmpeg 转码 / 字幕烧录 / 片段拼接 / 交叉淡化（`processing/` 完整）
- [x] 音频分析自动提取视频音轨（ffmpeg → wav → librosa）
- [x] API 设置面板（前端可配置后端地址 + LLM API Key）

- [ ] **【可选】视觉 LLM**：`vision.py` — 需用户配置 Qwen-VL / GPT-4V API Key
- [ ] **【可选】Whisper 模型下载**：首次运行自动下载 small 模型（~1GB）
- [ ] **【缺】端到端冒烟测试**：instances/ 下 3 个 .mov 的完整跑通验证
- [ ] **【缺】任务持久化**：`_jobs` dict 替换为 SQLite

---

## 三、里程碑规划

### M1: 独立模块搭建 ✅ 已完成 (v0.2.0)

- 目标：各层模块独立可运行
- 实际产出：信号层 6 通道、筛选层、脚本层 4 件套、处理层 3 工具、generation composer、前端拖拽框架均已实现

---

### M2: 打通三条关键链路 ✅ 已完成 (v0.5.0)

#### M2.1 — 理解层接入 ✅

| 任务 | 文件 | 状态 |
|------|------|------|
| 实现 `vision.py` API 调用 | `understanding/understand/vision.py` | ✅ 可配置，未配置时降级 |
| 实现 `structure.py` 的 `infer()` | `understanding/understand/structure.py` | ✅ 规则引擎 + 位置/活动 fallback |
| 帧提取工具 | `understanding/signal/frame_extractor.py` | ✅ OpenCV 按索引抽帧 PNG |

#### M2.2 — 管线模块树构建 ✅

| 任务 | 文件 | 状态 |
|------|------|------|
| 实现 `_build_module_tree()` | `backend/pipeline.py` | ✅ hook→title, talking_head→video_segment, montage→多段, conversion→subtitle, outro→video+effect |
| 集成 OCR 到管线 | `backend/pipeline.py` | ✅ `_run_ocr_on_keyframes()` 串联 FrameExtractor→OCRExtractor |
| 全组件降级保护 | `backend/pipeline.py` | ✅ 每个信号组件独立 try/except，缺失时跳过 |

#### M2.3 — 渲染链路贯通 ✅

| 任务 | 文件 | 状态 |
|------|------|------|
| HyperFrames CLI 调用 | `generation/renderer.py` | ✅ 含 FileNotFoundError/TimeoutExpired 处理 |
| FFmpeg concat fallback | `generation/renderer.py` | ✅ 标题卡片 MP4 渲染 |
| 端到端可运行 | — | ✅ 核心测试通过（31s 视频 → 11 个分段） |

#### M2.4 — 前端 API 对接 ✅

| 任务 | 文件 | 状态 |
|------|------|------|
| `handleUpload()` | `frontend/src/App.vue` | ✅ POST /upload + 状态轮询 |
| `handleAnalyze()` | `frontend/src/App.vue` | ✅ POST /analyze + 轮询至 completed |
| `handleExport()` | `frontend/src/App.vue` | ✅ POST /export + 轮询 + 下载 |
| API 设置面板 | `frontend/src/components/ApiSettingsPanelStatic.vue` | ✅ 后端地址 + LLM Key + 模型名 + Test Connection |
| InspectorPanel | `frontend/src/components/InspectorPanel.vue` | ✅ 类型/文本/字号/颜色/动画/转场/位置编辑 |
| 双通道工作台布局 | `frontend/src/App.vue` | ✅ 分析管线 + 生成管线 + 流程指示器 + 中文化 |

---

### M3: 前端功能完善（待开始）

**预计工时：2 周**

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 个性化注入面板 | 文本替换、样式参数编辑（InspectorPanel 扩展） | P0 |
| 素材槽位检测 | `source.path` 为空/文件缺失时高亮标记 + 补全建议 | P1 |
| 预览播放器 | 在画布区域按时间轴顺序展示模块 | P1 |
| WebSocket 任务状态推送 | 替换轮询，analysis/export 进度实时同步 | P2 |
| 导出配置面板 | 分辨率、码率、字幕样式选择 | P2 |
| 键盘快捷键 | Delete 删除选中模块，Ctrl+Z 撤销 | P2 |

---

### M4: 生成质量打磨（待开始）

**预计工时：2 周**

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 多类型视频模板 | Talking Head / Montage / Vlog / 教程 各类型 HTML 模板 | P0 |
| HyperFrames 或 FFmpeg 渲染落地 | 确认渲染引擎方案，实现至少一种可靠输出路径 | P0 |
| 模块间过渡平滑 | 自动插入交叉淡化转场片段 | P1 |
| 字幕渲染优化 | SRT 输出 + 中英双语字幕 + ASS 样式 | P1 |
| 批量生成性能 | 多视频并行分析、多导出任务队列 | P2 |

---

### M5: 稳定性与发布（待开始）

**预计工时：1 周**

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 异常流程处理 | 上传失败、分析超时、API 错误重试、生成崩溃恢复 | P0 |
| 任务持久化 | `_jobs` dict 替换为 SQLite/Redis，进程重启不丢失 | P0 |
| 长视频分片处理 | >10 分钟视频的分段分析 + 结果合并 | P1 |
| 错误日志与监控 | structlog 接入，各环节耗时统计 | P2 |
| 使用文档 | 部署指南 + API 文档 + 用户手册 | P2 |
| 内存优化 | OpenCV `VideoCapture` 即时释放、大视频流式处理 | P2 |

---

## 四、技术架构图

```
┌──────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3)                      │
│  双通道工作台：分析管线 ── 生成管线                         │
│  拖拽时间轴 │ 属性检查器 │ API 设置面板                    │
└─────────────────────┬────────────────────────────────────┘
                      │ REST (polling)
┌─────────────────────▼────────────────────────────────────┐
│                  Backend (FastAPI)                        │
│  routers: upload / analyze / export                       │
│  pipeline.py: 管线状态机编排                              │
│  全组件懒加载 + 独立降级                                   │
└───┬──────────┬──────────┬──────────┬─────────────────────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌────────┐┌────────┐┌────────┐┌──────────┐
│ Signal ││ Filter ││Underst.││ Script   │
│ (本地) ││ (本地) ││ (本地+ ││ Engine   │
│        ││        ││ 可选云)││          │
│OpenCV  ││Adaptive││规则引擎││Schema    │
│PyScene ││Sampler ││+ LLM   ││Builder   │
│Whisper ││        ││        ││Manipul.  │
│Librosa ││        ││        ││Validator │
│Tesser. ││        ││        ││          │
└───┬────┘└───┬────┘└────────┘└────┬─────┘
    │         │                    │
    └────┬────┘                    │
         ▼                         ▼
┌─────────────────┐    ┌───────────────────┐
│  Generation     │    │   Processing       │
│  HyperFrames    │    │   FFmpeg           │
│  composer.py    │───▶│   transcoder.py    │
│  renderer.py    │    │   subtitle.py      │
│  templates/     │    │   concat.py        │
└─────────────────┘    │   ffmpeg_utils.py  │
                       └───────────────────┘
```

---

## 五、可迁移脚本数据流

```
原始视频
  │
  ├─ signal/  ──▶ 帧差矩阵 + 场景边界 + 语音文本 + BPM + OCR 区域 + 帧图像
  │                 ↑ 任何组件失败自动跳过，不影响后续
  │
  ├─ filter/  ──▶ 筛选后的关键帧序列（N 帧 + 时间戳 + 信号上下文）
  │
  ├─ understand/ ──▶ 结构化模块树
  │                   ├─ 位置检测 → Hook / Outro
  │                   ├─ 快切检测 → Montage
  │                   ├─ 语音时长 → Talking Head
  │                   └─ OCR 规则 → Title / CTA / Logo
  │
  ├─ script/   ──▶ 可迁移脚本 JSON（符合 schema.py 定义）
  │                  │
  │     ┌────────────┼────────────┐
  │     ▼            ▼            ▼
  │  builder.py  manipulator  validator.py
  │  (构建)      .py(操作)    (校验)
  │
  ├─ frontend/ ──▶ 用户拖拽编辑 + InspectorPanel 参数调整
  │
  └─ generation/ + processing/ ──▶ MP4
```

---

## 六、本地依赖一览

| 组件 | 依赖包 | 大小 | 必需？ |
|------|--------|------|--------|
| 帧差 + 帧提取 | opencv-python | ~90 MB | ✅ 必需 |
| 场景检测 | scenedetect | ~1 MB | ✅ 必需 |
| 语音转写 | openai-whisper + torch | ~2 GB | ⬜ 可选（无则跳过） |
| 音频分析 | librosa | ~80 MB | ⬜ 可选（无则跳过） |
| 音频提取 | ffmpeg | ~100 MB | ⬜ 可选（无则跳过） |
| 文字识别 | pytesseract + Tesseract | ~50 MB | ⬜ 可选（无则跳过） |
| 视觉理解 | Qwen-VL / GPT-4V API | 0 (云端) | ⬜ 可选（需 API Key） |

**最小可用配置**：仅 opencv-python + scenedetect（~90MB），可进行帧差 + 场景检测 + 结构推理。

---

## 七、版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1.0 | 2025-07-25 | 项目启动，技术选型与架构设计 |
| v0.2.0 | 2026-05-30 | 六模块基础代码搭建完成 |
| v0.3.0 | 2026-05-30 | 制定项目计划，进入联调与打磨阶段 |
| v0.4.0 | 2026-07-14 | 全量代码审查：校准完成度、发现 6 个阻断缺口、重构里程碑 |
| v0.5.0 | 2026-05-30 | M2 完成：结构推理规则引擎、管线模块树、渲染双路径、前端双通道工作台、全中文化、全组件降级保护、OCR 改为 Tesseract |
