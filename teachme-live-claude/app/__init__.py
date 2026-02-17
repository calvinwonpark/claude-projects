"""Package shim so `uvicorn app:app` resolves to the root ASGI app lazily."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_ROOT_APP = Path(__file__).resolve().parent.parent / "app.py"
_CACHED_APP = None


def _load_asgi_app():
    global _CACHED_APP
    if _CACHED_APP is not None:
        return _CACHED_APP
    spec = spec_from_file_location("teachme_live_claude_root_app", _ROOT_APP)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load ASGI module from {_ROOT_APP}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    _CACHED_APP = module.app
    return _CACHED_APP


def __getattr__(name):
    if name == "app":
        return _load_asgi_app()
    raise AttributeError(name)


__all__ = ["app"]
