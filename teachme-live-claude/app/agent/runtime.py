"""Bridge module that exposes top-level agent runtime inside app package imports."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_RUNTIME_FILE = Path(__file__).resolve().parents[2] / "agent" / "runtime.py"
_SPEC = spec_from_file_location("teachme_live_claude_top_runtime", _RUNTIME_FILE)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load runtime module from {_RUNTIME_FILE}")
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

build_structured_system_prompt = _MODULE.build_structured_system_prompt
parse_structured_json = _MODULE.parse_structured_json
run_tutor_turn = _MODULE.run_tutor_turn
safe_structured_fallback = _MODULE.safe_structured_fallback
is_image_required_query = _MODULE.is_image_required_query
is_math_like_query = _MODULE.is_math_like_query
AgentRuntimeResult = _MODULE.AgentRuntimeResult
