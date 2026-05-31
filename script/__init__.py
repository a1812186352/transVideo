"""Script layer: JSON schema, builder, manipulator, validator.

Provides tools to define, build, manipulate, and validate MigratableScript
JSON documents — a renderer-agnostic video project format.

Typical usage::

    from script import (
        MIGRATABLE_SCRIPT_SCHEMA,
        ScriptBuilder,
        ScriptManipulator,
        ScriptValidator,
    )

    builder = ScriptBuilder()
    script = builder.create_empty_script("My Project")
    # ... add modules via ScriptManipulator ...
    validator = ScriptValidator(MIGRATABLE_SCRIPT_SCHEMA)
    issues = validator.validate(script)
"""

from script.schema import MIGRATABLE_SCRIPT_SCHEMA
from script.builder import ScriptBuilder
from script.manipulator import ScriptManipulator
from script.validator import ScriptValidator

__all__ = [
    "MIGRATABLE_SCRIPT_SCHEMA",
    "ScriptBuilder",
    "ScriptManipulator",
    "ScriptValidator",
]
