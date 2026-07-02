"""Blender test runner.

Run from the repo root:
    blender --background --python tests/run_tests.py

The step_importer addon must be installed in Blender or the repo root must be
on sys.path (which this script ensures automatically).
"""
import glob
import os
import sys
import unittest
import zipfile

# Ensure repo root is on sys.path so `step_importer` resolves as a package.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# When installed as a real extension, Blender extracts the bundled cascadio
# wheel into its own site-packages and adds that to sys.path automatically.
# Running the dev copy straight off disk (as this script does) skips that
# step, so `import cascadio` would otherwise fail — extract the
# platform-matching wheel into a local cache dir and add it to sys.path too.
# (cascadio ships a compiled `_core` extension module, which Python cannot
# import directly out of a zipped .whl, so the wheel must be unpacked first.)
_WHEELS_DIR = os.path.join(REPO_ROOT, "step_importer", "wheels")
_WHEEL_CACHE = os.path.join(os.path.dirname(__file__), ".wheel_cache")
_matches = glob.glob(os.path.join(_WHEELS_DIR, "*win_amd64.whl"))
if _matches:
    _whl_path = _matches[0]
    _extract_dir = os.path.join(_WHEEL_CACHE, os.path.splitext(os.path.basename(_whl_path))[0])
    if not os.path.isdir(_extract_dir):
        with zipfile.ZipFile(_whl_path) as _zf:
            _zf.extractall(_extract_dir)
    if _extract_dir not in sys.path:
        sys.path.insert(0, _extract_dir)

loader = unittest.TestLoader()
suite = loader.discover(start_dir=os.path.dirname(__file__), pattern="test_*.py")

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

sys.exit(0 if result.wasSuccessful() else 1)
