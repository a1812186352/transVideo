"""JSON Schema definition for the Migratable Script format (draft-07).

Defines the complete schema for video project scripts that can be migrated
across different rendering engines.
"""

from typing import Dict, Any

MIGRATABLE_SCRIPT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft-07/schema#",
    "$id": "https://transvideo.dev/schema/migratable-script.json",
    "title": "MigratableScript",
    "description": "A renderer-agnostic video project script that can be "
                   "mapped to HyperFrames, Remotion, or FFmpeg pipelines.",
    "type": "object",
    "required": ["version", "metadata", "modules"],
    "additionalProperties": False,
    "properties": {
        "version": {
            "type": "string",
            "description": "Schema version semver.",
            "pattern": r"^\d+\.\d+\.\d+$",
        },
        "metadata": {
            "type": "object",
            "required": ["title", "created_at", "total_duration"],
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "author": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "total_duration": {
                    "type": "number",
                    "description": "Total duration in seconds.",
                    "minimum": 0,
                },
                "source_video_id": {"type": "string"},
                "fps": {"type": "number", "minimum": 1},
                "resolution": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "width": {"type": "integer", "minimum": 1},
                        "height": {"type": "integer", "minimum": 1},
                    },
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "modules": {
            "type": "array",
            "description": "Ordered list of timeline modules.",
            "minItems": 1,
            "items": {"$ref": "#/definitions/Module"},
        },
        "tracks": {
            "type": "array",
            "description": "Track definitions for multi-track layout.",
            "items": {"$ref": "#/definitions/Track"},
        },
    },
    "definitions": {
        "Module": {
            "type": "object",
            "required": ["id", "type", "start_time", "duration", "track_index"],
            "additionalProperties": False,
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Unique module identifier.",
                },
                "type": {
                    "type": "string",
                    "enum": [
                        "title",
                        "video_segment",
                        "subtitle",
                        "transition",
                        "audio",
                        "effect",
                    ],
                },
                "label": {
                    "type": "string",
                    "description": "Human-readable module name.",
                },
                "start_time": {
                    "type": "number",
                    "description": "Start time in seconds.",
                    "minimum": 0,
                },
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds.",
                    "minimum": 0,
                },
                "track_index": {
                    "type": "integer",
                    "description": "Which track this module belongs to.",
                    "minimum": 0,
                },
                "source": {
                    "type": "object",
                    "description": "Source material reference.",
                    "additionalProperties": False,
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["video", "image", "text", "audio", "effect"],
                        },
                        "path": {"type": "string"},
                        "start_offset": {"type": "number"},
                        "end_offset": {"type": "number"},
                    },
                },
                "params": {
                    "type": "object",
                    "description": "Renderer-agnostic parameters.",
                    "additionalProperties": False,
                    "properties": {
                        "text_content": {"type": "string"},
                        "font_size": {"type": "integer"},
                        "font_color": {"type": "string"},
                        "position": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                        },
                        "animation": {"type": "string"},
                        "volume": {"type": "number", "minimum": 0, "maximum": 1},
                        "transition_type": {"type": "string"},
                    },
                },
                "children": {
                    "type": "array",
                    "description": "Nested sub-modules.",
                    "items": {"$ref": "#/definitions/Module"},
                },
            },
        },
        "Track": {
            "type": "object",
            "required": ["index", "name", "type"],
            "additionalProperties": False,
            "properties": {
                "index": {"type": "integer", "minimum": 0},
                "name": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["video", "audio", "text", "effect"],
                },
                "muted": {"type": "boolean"},
                "locked": {"type": "boolean"},
            },
        },
    },
}
