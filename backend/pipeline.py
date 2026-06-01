"""Pipeline — thin entry point that delegates to understanding.pipeline_orchestrator.

Kept for backward compatibility: all existing ``from backend.pipeline import Pipeline``
imports continue to work unchanged.
"""

from understanding.pipeline_orchestrator import Pipeline, _lazy_import

__all__ = ["Pipeline", "_lazy_import"]
