"""Blender test runner.

Run from the repo root:
    blender --background --python tests/run_tests.py

The step_importer addon must be installed in Blender or the repo root must be
on sys.path (which this script ensures automatically).
"""
import os
import sys
import unittest

# Ensure repo root is on sys.path so `step_importer` resolves as a package.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

loader = unittest.TestLoader()
suite = loader.discover(start_dir=os.path.dirname(__file__), pattern="test_*.py")

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

sys.exit(0 if result.wasSuccessful() else 1)
