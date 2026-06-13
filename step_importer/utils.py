import os

_STEP_EXTENSIONS = frozenset({".step", ".stp"})
_IGES_EXTENSIONS = frozenset({".iges", ".igs"})


def detect_file_type(filepath: str) -> str:
    """Return ``'step'`` or ``'iges'`` based on *filepath*'s extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in _STEP_EXTENSIONS:
        return "step"
    if ext in _IGES_EXTENSIONS:
        return "iges"
    raise ValueError(f"Unrecognised file extension: {ext!r}")


def cascadio_available() -> bool:
    """Return ``True`` if cascadio is importable (wheels are bundled)."""
    try:
        import cascadio  # noqa: F401

        return True
    except ImportError:
        return False
