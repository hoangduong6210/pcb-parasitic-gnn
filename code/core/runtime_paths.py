"""Runtime path helpers shared by source and reorganized release layouts."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def resolve_module_file(module_name: str) -> Path:
    """Return an importable module's source path without importing it.

    The research tree keeps modules flat in ``04_code`` while the public release
    groups them into themed directories on ``PYTHONPATH``.  Resolving through the
    import system avoids assumptions about either physical layout.
    """
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise FileNotFoundError(f"Cannot resolve importable module: {module_name}")
    path = Path(spec.origin).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Resolved module is not a file: {path}")
    return path


def fem_cps_worker_path() -> Path:
    """Resolve the isolated gmsh worker in source or release layouts."""
    return resolve_module_file("fem_cps_worker")


def fem_cps_diagnostic_worker_path() -> Path:
    """Resolve the mesh/domain diagnostic worker in source or release layouts."""
    return resolve_module_file("fem_cps_diagnostic_worker")
