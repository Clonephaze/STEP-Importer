"""Pure unit tests — no Blender or cascadio required.

These tests cover logic that is entirely self-contained Python and can run
with a plain `python -m pytest tests/test_units.py` or inside Blender.
"""
import importlib.util
import os
import sys
import types
import unittest
from math import pi

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_pkg_dir = os.path.join(REPO_ROOT, "step_importer")

# ── Stub every external dependency before any step_importer code loads ────────
# NOTE: run_tests.py discovers this file into the *same* Python process as
# test_import.py, which needs the real bpy/mathutils/step_importer. So the
# stub modules below are only kept in sys.modules for as long as it takes to
# exec_module() the test copies of utils.py/importer.py — the originals
# (or nothing, if this file is run standalone outside Blender) are restored
# immediately afterward.

_STUB_MODULE_NAMES = (
    "bpy", "bpy.props", "bpy.types", "bpy_extras", "bpy_extras.io_utils",
    "mathutils", "step_importer", "step_importer.operators",
    "step_importer.preferences", "step_importer.progress",
    # These two get overwritten below with test copies (built with the fake
    # bpy/mathutils bound in *their* module globals via `import bpy` /
    # `from mathutils import Matrix`). They must also be evicted afterward so
    # that the real step_importer package re-imports fresh, real-bpy-bound
    # copies instead of reusing these cached fakes.
    "step_importer.utils", "step_importer.importer",
)
_original_modules = {name: sys.modules.get(name) for name in _STUB_MODULE_NAMES}


def _restore_original_modules():
    """Undo the stubbing above so the real bpy/mathutils/step_importer
    (when present, e.g. inside Blender) are visible to other test modules."""
    for name, mod in _original_modules.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _empty_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

# bpy stubs — operators.py imports specific names from bpy.props
_bpy = _empty_module("bpy")
_bpy_props = _empty_module("bpy.props")
_bpy_types = _empty_module("bpy.types")
for _sym in ("BoolProperty", "EnumProperty", "FloatProperty", "StringProperty",
             "IntProperty"):
    setattr(_bpy_props, _sym, lambda *a, **kw: None)

_bpy_extras = _empty_module("bpy_extras")
_bpy_extras_io = _empty_module("bpy_extras.io_utils")
_bpy_extras_io.ImportHelper = object

# mathutils stub — _build_correction uses Matrix
class _FakeMatrix:
    """Minimal Matrix stub that records the operations applied."""
    def __init__(self, label="I"):
        self._label = label

    @staticmethod
    def Identity(n):
        return _FakeMatrix("I")

    @staticmethod
    def Rotation(angle, size, axis):
        return _FakeMatrix(f"R({axis},{angle:.4f})")

    def __matmul__(self, other):
        return _FakeMatrix(f"({self._label} @ {other._label})")

    def __eq__(self, other):
        return isinstance(other, _FakeMatrix) and self._label == other._label

    def __repr__(self):
        return f"Matrix({self._label})"

_mathutils = _empty_module("mathutils")
_mathutils.Matrix = _FakeMatrix

# step_importer package stubs — stop __init__.py from loading operators etc.
_pkg = _empty_module("step_importer")
_pkg.__path__ = [_pkg_dir]
_pkg.__package__ = "step_importer"
_empty_module("step_importer.operators")
_empty_module("step_importer.preferences")
_empty_module("step_importer.progress")

# Provide a real ViewportProgressBar stub inside the progress stub
class _NoOpProgressBar:
    def __init__(self, *a, **kw): pass
    def update(self, *a, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

sys.modules["step_importer.progress"].ViewportProgressBar = _NoOpProgressBar

# ── Load utils and importer directly (bypassing __init__.py) ─────────────────

def _load(mod_name, filename):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(_pkg_dir, filename))
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "step_importer"
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

_utils_mod   = _load("step_importer.utils",    "utils.py")
_importer_mod = _load("step_importer.importer", "importer.py")

detect_file_type  = _utils_mod.detect_file_type
_real_build_correction = _importer_mod._build_correction

# Now that the test copies of utils.py/importer.py are loaded, put the real
# bpy/mathutils/step_importer (if any) back so the rest of the test process
# — notably test_import.py — sees the genuine modules again.
_restore_original_modules()


def _build_correction(up_axis, rotation_deg):
    """Call the real _build_correction with the fake mathutils in place.

    _build_correction does ``from mathutils import Matrix`` inside its own
    body, so the fake only needs to be visible in sys.modules for the
    duration of this call, not globally.
    """
    orig = sys.modules.get("mathutils")
    sys.modules["mathutils"] = _mathutils
    try:
        return _real_build_correction(up_axis, rotation_deg)
    finally:
        if orig is None:
            sys.modules.pop("mathutils", None)
        else:
            sys.modules["mathutils"] = orig


# ── detect_file_type tests ────────────────────────────────────────────────────

class TestDetectFileType(unittest.TestCase):

    def test_step_extensions(self):
        for ext in (".step", ".STEP", ".stp", ".STP"):
            with self.subTest(ext=ext):
                self.assertEqual(detect_file_type(f"model{ext}"), "step")

    def test_iges_extensions(self):
        for ext in (".iges", ".IGES", ".igs", ".IGS"):
            with self.subTest(ext=ext):
                self.assertEqual(detect_file_type(f"model{ext}"), "iges")

    def test_unknown_extension_raises(self):
        with self.assertRaises(ValueError):
            detect_file_type("model.obj")

    def test_path_with_directories(self):
        self.assertEqual(detect_file_type("/some/deep/path/part.step"), "step")


# ── _build_correction tests ───────────────────────────────────────────────────

class TestBuildCorrection(unittest.TestCase):

    def test_z_up_no_spin_is_identity(self):
        """up_axis=Z with 0 rotation should be a spin-of-zero @ identity."""
        result = _build_correction("Z", 0.0)
        # spin(0) @ Identity — both are effectively identity
        self.assertIsInstance(result, _FakeMatrix)

    def test_y_up_applies_x_rotation(self):
        """up_axis=Y should apply a -90° rotation around X."""
        result = _build_correction("Y", 0.0)
        half = pi / 2
        expected_up = _FakeMatrix.Rotation(-half, 4, 'X')
        expected_spin = _FakeMatrix.Rotation(0.0, 4, 'Z')
        expected = expected_spin @ expected_up
        self.assertEqual(result, expected)

    def test_minus_z_up_applies_180_x_rotation(self):
        result = _build_correction("MINUS_Z", 0.0)
        expected_up = _FakeMatrix.Rotation(pi, 4, 'X')
        expected_spin = _FakeMatrix.Rotation(0.0, 4, 'Z')
        self.assertEqual(result, expected_spin @ expected_up)

    def test_spin_is_applied_after_up_correction(self):
        """Rotation degrees should produce a spin matrix composed after up correction."""
        result = _build_correction("Z", 90.0)
        from math import radians
        expected_spin = _FakeMatrix.Rotation(radians(90.0), 4, 'Z')
        expected_up = _FakeMatrix.Identity(4)
        self.assertEqual(result, expected_spin @ expected_up)

    def test_unknown_up_axis_falls_back_to_identity(self):
        """An unrecognised up_axis value should not raise — falls back to identity."""
        try:
            _build_correction("BOGUS", 0.0)
        except Exception as exc:
            self.fail(f"_build_correction raised unexpectedly: {exc}")

    def test_all_valid_axes_do_not_raise(self):
        for axis in ("X", "Y", "Z", "MINUS_X", "MINUS_Y", "MINUS_Z"):
            with self.subTest(axis=axis):
                _build_correction(axis, 0.0)


if __name__ == "__main__":
    unittest.main()
