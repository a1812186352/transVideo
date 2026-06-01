"""Result assembly and persistence helpers.

Exported functions:
    assemble_result(...)  — build the final pipeline return dict
"""

from typing import Any, Dict, List, Optional


def assemble_result(
    signal_data: Dict[str, Any],
    keyframes: List[dict],
    structure_segments: List[dict],
    module_tree: List[Dict[str, Any]],
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the final analysis result dict.

    Args:
        signal_data: Raw signal layer outputs.
        keyframes: Sampled keyframe metadata.
        structure_segments: Narrative structure segments.
        module_tree: Typed module list for script building.
        job_id: Optional job identifier for store integration.

    Returns:
        Dict with keys: signal_data, keyframes, structure, module_tree.
        (job_id if provided.)
    """
    result: Dict[str, Any] = {
        "signal_data": signal_data,
        "keyframes": keyframes,
        "structure": structure_segments,
        "module_tree": module_tree,
    }
    if job_id:
        result["job_id"] = job_id
    return result
