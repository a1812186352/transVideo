# Credits

## 贡献者

**a1812186352** — 核心思路、任务拆解、产品设计、关键功能实现

从项目立项到 v0.5 的完整迭代中，主导了以下工作：

### 产品与架构设计
- 定义"视频结构拆解 → 可迁移脚本 → 个性化生成"三层产品范式
- 设计五层流水线架构（信号层 → 筛选层 → 理解层 → 编排层 → 生成层），确保每一层可独立降级、可替换
- 确立"纯本地运行、零外部 API 依赖"的核心原则，所有 ML 组件均设计为可选 + 自动降级

### 功能实现
- **信号层六通道**：帧差分析、场景检测、Whisper 语音转录、Librosa 音频分析、Tesseract OCR、OpenCV 帧提取的集成与容错编排
- **自适应采样策略**：百分位阈值 + 场景边界交并判定 + 平坦曲线均匀采样 fallback
- **5 类型规则引擎**：Opening / Highlight / Transition / Effect / Closing 滑窗分类器，含视觉特征（人脸、光流、YOLO、饱和度、边缘密度）多信号融合
- **可迁移脚本系统**：JSON Schema 定义 + Pydantic 双源校验 + Builder / Manipulator / Validator 三件套
- **前端双通道工作台**：Vue 3 拖拽时间轴、InspectorPanel 参数编辑、SSE 实时 Monitor、缩略图轨道
- **生成层双路径渲染**：HyperFrames HTML 模板 + FFmpeg 硬编码 fallback
- **FFmpeg 处理管线**：转码、字幕烧录、分段拼接、交叉淡化（xfade）
- **YOLOv8 物体检测集成**：自动下载 + 优雅降级链（API → YOLO → OpenCV 零模型）
- **ThumbnailStrip 组件**：单向同步缩略图轨道，hover 放大，拖拽定位
- **ScriptEditor / MaterialPanel**：分镜解析与素材管理

### 工程化
- 全组件懒加载 + 独立降级保护，任何 ML 组件缺失不影响其余分析
- 端到端集成测试（pytest），覆盖三条核心链路
- SQLite JobStore 持久化 + SSE 实时进度推送
- 项目清理、依赖精简、`.gitignore` 与文档维护
