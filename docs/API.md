# transVideo API 文档

> 版本 v1.0.0 · 2026-07-14
> 基础路径：`http://localhost:8000`

---

## 健康检查

### `GET /`

返回服务基本信息。

**响应 200**
```json
{"service": "transVideo", "version": "0.1.0", "status": "running"}
```

### `GET /health`

**响应 200**
```json
{"status": "healthy"}
```

---

## 上传

### `POST /upload/`

上传视频文件。

**请求**：`multipart/form-data`，字段 `file`

**验证**：
- 扩展名：`.mp4 .mov .avi .webm .mkv .mpeg .mpg .m4v .3gp .3g2`
- MIME：`video/mp4 video/quicktime video/x-msvideo video/webm video/x-matroska ...`
- 大小上限：2 GB
- 并发上限：每个 IP 3 个

**响应 200**
```json
{
  "video_id": "a1b2c3d4e5f6g7h8",
  "filename": "demo.mp4",
  "size_bytes": 1048576,
  "duration": 30.0,
  "width": 1920,
  "height": 1080,
  "fps": 30.0
}
```

**错误**：`400` 文件类型不支持 · `413` 超过 2 GB · `422` 未提供文件

### `GET /upload/video/{video_id}`

流式播放上传的视频。

**响应 200**：`video/mp4` 流，支持 `Range` 头部。

### `GET /upload/video/{video_id}/thumbnails?interval=3.0`

间隔提取缩略图。

**响应 200**
```json
[
  {"timestamp": 0.0, "data_uri": "data:image/jpeg;base64,..."},
  {"timestamp": 3.0, "data_uri": "data:image/jpeg;base64,..."}
]
```

### `GET /upload/video/{video_id}/filmstrip?count=20`

均匀分布的电影条缩略图（用于时间轴预览）。

**响应 200**：同 `/thumbnails` 格式，`count` 范围 5-100。

### `GET /upload/video/{video_id}/thumbnail?time=0.0`

提取单帧 JPEG。

**响应 200**：`image/jpeg` · **404** 视频不存在 · **500** 解码失败

---

## 分析

### `POST /analyze/{video_id}`

触发视频分析管线（信号→过滤→理解→脚本）。

**响应 200**
```json
{"video_id": "a1b2c3d4e5f6g7h8", "status": "processing"}
```

**错误**：`404` 视频未找到 · `409` 分析已在进行中

### `GET /analyze/{video_id}`

轮询分析状态。

**响应 200**
```json
{
  "video_id": "a1b2c3d4e5f6g7h8",
  "status": "completed",
  "script": {"version": "1.0.0", "modules": [...], ...}
}
```

状态：`processing` → `completed` / `failed`

### `GET /analyze/{video_id}/stream`

SSE 实时推送分析进度。

**事件格式**
```
data: {"type": "progress", "tag": "frame_diff", "msg": "正在分析帧差异…"}
data: {"type": "segment", "index": 0, "module": {...}}
data: {"type": "done", "total": 12, "elapsed": 45.2}
data: {"type": "error", "message": "分析失败"}
```

---

## 导出（渲染）

### `POST /export/{video_id}`

提交渲染任务。请求体为完整的 MigratableScript JSON。

**请求体**
```json
{
  "version": "1.0.0",
  "metadata": {"title": "项目", "total_duration": 30.0, "fps": 30.0},
  "modules": [
    {"id": "m1", "type": "title", "start_time": 0.0, "duration": 3.0, ...},
    {"id": "m2", "type": "video_segment", "start_time": 3.0, "duration": 27.0, ...}
  ],
  "tracks": [...]
}
```

**响应 200**
```json
{"video_id": "a1b2c3d4e5f6g7h8", "status": "queued", "output_path": null, "error": null}
```

**错误**：`422` 脚本校验失败 · `409` 渲染已在进行中

### `GET /export/{video_id}`

轮询渲染状态。

**响应 200**
```json
{
  "video_id": "a1b2c3d4e5f6g7h8",
  "status": "completed",
  "output_path": "export/output/a1b2_output.mp4",
  "error": null
}
```

### `GET /export/output/{filename}`

下载渲染产物。

**响应 200**：`video/mp4` · **404** 文件不存在 · **403** 路径穿越

### `GET /export/{video_id}/progress`

SSE 实时推送渲染进度。

**事件格式**
```
data: {"progress": 23, "stage": "提取视频段并裁剪", "eta": 180}
data: {"progress": 100, "stage": "完成", "eta": 0}
```

### `POST /export/{video_id}/cancel`

取消正在运行的渲染任务。

**响应 200**：`{"video_id": "...", "status": "canceled"}` · **404** 任务不存在 · **409** 无法取消（已完成/失败）

---

## 素材管理

### `POST /materials/upload`

上传参考图片或视频片段。

**支持格式**：`.jpg .jpeg .png .webp .mp4 .webm .mov` · 上限 50 MB

**响应 200**
```json
{
  "material_id": "abc123def456",
  "filename": "ref.png",
  "ext": ".png",
  "size_bytes": 102400,
  "thumbnail": "data:image/jpeg;base64,..."
}
```

### `GET /materials/list`

列出所有素材。

### `DELETE /materials/{material_id}`

删除素材。**200** 成功 · **404** 不存在

### `POST /materials/check`

检查文件路径是否存在（前端路径验证用）。

**请求**
```json
{"paths": ["D:/video.mp4", "/img/bg.png"]}
```

**响应**
```json
{"results": [{"path": "D:/video.mp4", "status": "ok", ...}, ...]}
```

---

## 恢复

### `GET /recovery/status`

返回各 namespace 的陈旧任务计数。

### `POST /recovery/analyze/{video_id}`

断点恢复分析任务。跳过已完成的 stage。

---

## 指标

### `GET /metrics`

Prometheus 格式指标。
