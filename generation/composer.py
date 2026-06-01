"""Composer: Maps MigratableScript JSON to HyperFrames HTML.

Transforms the renderer-agnostic script JSON into a HyperFrames-compatible
HTML document with data-* attributes for declarative rendering.
"""

import json
from typing import Any, Dict, List
from string import Template


class Composer:
    """Maps MigratableScript JSON to HyperFrames HTML structure.

    Attributes:
        template_path: Path to a HyperFrames HTML template file.
    """

    def __init__(self, template_path: str = "") -> None:
        self.template_path = template_path

    def script_to_html(self, script: Dict[str, Any]) -> str:
        """Convert a MigratableScript to HyperFrames HTML.

        The output HTML uses data-* attributes for declarative module
        placement: data-start (seconds), data-duration (seconds),
        data-track-index (integer), data-type (module type).

        Args:
            script: Complete MigratableScript dict.

        Returns:
            Complete HyperFrames HTML document as a string.
        """
        template = self._load_template()
        modules = script.get("modules", [])
        metadata = script.get("metadata", {})
        tracks = script.get("tracks", [])

        # Build track containers
        track_html = self._build_tracks_html(tracks, modules)

        # Build module elements
        module_elements = self._build_module_elements(modules)

        # Fill template
        html = Template(template).safe_substitute(
            title=metadata.get("title", "Untitled"),
            width=(metadata.get("resolution") or {}).get("width", 1920),
            height=(metadata.get("resolution") or {}).get("height", 1080),
            fps=metadata.get("fps", 30),
            total_duration=metadata.get("total_duration", 0.0),
            tracks=track_html,
            modules=module_elements,
            script_json=json.dumps(script, indent=2, ensure_ascii=False, default=str),
        )

        return html

    def _load_template(self) -> str:
        """Load HTML template from file or use default."""
        if self.template_path:
            try:
                with open(self.template_path, "r", encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                pass

        return DEFAULT_TEMPLATE

    def _build_tracks_html(
        self, tracks: List[Dict[str, Any]], modules: List[Dict[str, Any]]
    ) -> str:
        """Build HTML for track containers."""
        if not tracks:
            # Auto-generate tracks from modules
            track_indices = sorted(set(m.get("track_index", 0) for m in modules))
            tracks = [
                {"index": i, "name": f"Track {i}", "type": "video"}
                for i in track_indices
            ]

        lines: List[str] = []
        for track in tracks:
            lines.append(
                f'<div class="hyper-track" '
                f'data-track-index="{track["index"]}" '
                f'data-track-name="{track["name"]}" '
                f'data-track-type="{track["type"]}">'
                f'</div>'
            )
        return "\n".join(lines)

    def _build_module_elements(self, modules: List[Dict[str, Any]]) -> str:
        """Build HTML fragment for each module."""
        lines: List[str] = []
        for mod in modules:
            params = mod.get("params") or {}
            source = mod.get("source") or {}

            attrs = {
                "data-module-id": mod["id"],
                "data-type": mod["type"],
                "data-start": str(mod.get("start_time", 0)),
                "data-duration": str(mod.get("duration", 0)),
                "data-track-index": str(mod.get("track_index", 0)),
            }

            if mod.get("label"):
                attrs["data-label"] = mod["label"]

            if source.get("path"):
                attrs["data-source-path"] = source["path"]

            if params.get("text_content"):
                attrs["data-text"] = params["text_content"]

            if params.get("animation"):
                attrs["data-animation"] = params["animation"]

            if params.get("transition_type"):
                attrs["data-transition"] = params["transition_type"]

            attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())

            inner_content = ""
            if mod["type"] == "title" and params.get("text_content"):
                inner_content = params["text_content"]
            elif mod["type"] == "subtitle" and params.get("text_content"):
                inner_content = params["text_content"]

            if inner_content:
                lines.append(f"<div {attr_str}>{inner_content}</div>")
            else:
                lines.append(f"<div {attr_str}></div>")

        return "\n".join(lines)


# Default HyperFrames HTML template
DEFAULT_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>$title</title>
  <style>
    :root {
      --canvas-width: ${width}px;
      --canvas-height: ${height}px;
      --track-height: 120px;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #1a1a2e;
      font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
      overflow: hidden;
    }
    .hyper-canvas {
      position: relative;
      width: var(--canvas-width);
      height: var(--canvas-height);
      margin: 0 auto;
      background: #000;
      overflow: hidden;
    }
    .hyper-track {
      position: absolute;
      left: 0;
      right: 0;
      height: var(--track-height);
      background: rgba(255, 255, 255, 0.03);
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .hyper-track[data-track-index="0"] { top: 0; }
    .hyper-track[data-track-index="1"] { top: var(--track-height); }
    .hyper-track[data-track-index="2"] { top: calc(var(--track-height) * 2); }
    .hyper-track[data-track-index="3"] { top: calc(var(--track-height) * 3); }
    .hyper-track[data-track-index="4"] { top: calc(var(--track-height) * 4); }
    .hyper-module {
      position: absolute;
      overflow: hidden;
      border-radius: 4px;
    }
    [data-type="title"] {
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 48px;
      font-weight: 700;
      color: #fff;
      text-shadow: 0 2px 12px rgba(0, 0, 0, 0.5);
    }
    [data-type="subtitle"] {
      display: flex;
      align-items: flex-end;
      justify-content: center;
      padding-bottom: 40px;
      font-size: 28px;
      color: #fff;
      text-shadow: 0 1px 4px rgba(0, 0, 0, 0.8);
    }
    [data-type="video_segment"] {
      background: #0a0a1a;
    }
    [data-type="transition"] {
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
    }
    [data-type="effect"] {
      background: rgba(255, 255, 255, 0.05);
      pointer-events: none;
    }
  </style>
</head>
<body>
  <div class="hyper-canvas" data-fps="$fps" data-duration="$total_duration">
    $tracks
  </div>
  <!-- Module definitions (rendered by HyperFrames engine) -->
  <!-- $modules -->
  <!-- Embedded script JSON for reference -->
  <script type="application/json" id="migratable-script">
    $script_json
  </script>
</body>
</html>"""
