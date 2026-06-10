"""Backend store package — SQLite-backed persistence.

Re-exports everything from ``backend.store.job_store`` for
backward compatibility with ``from backend.store import ...``.
"""

from backend.store.job_store import (  # noqa: F401
    # ── Main store class ──
    JobStore,
    # ── Stage constants ──
    STAGE_FRAME_DIFF,
    STAGE_SCENE_DETECT,
    STAGE_AUDIO_TRANSCRIBE,
    STAGE_AUDIO_ANALYSIS,
    STAGE_VISUAL_FEATURES,
    STAGE_STRUCTURE,
    STAGE_SCRIPT_BUILD,
    CHECKPOINT_STAGES,

)
