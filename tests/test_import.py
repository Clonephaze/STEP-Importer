"""Integration tests for the STEP import pipeline.

Requires a real Blender environment with cascadio wheels installed.
Run via:
    blender --background --python tests/run_tests.py

Place fixture .step files in tests/fixtures/ before running.
"""
import os
import unittest

import bpy

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


class TestSTEPImport(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)

    def test_import_creates_mesh_objects(self):
        """Importing a STEP fixture produces at least one mesh object."""
        path = _fixture("simple_cube.step")
        if not os.path.exists(path):
            self.skipTest("Fixture not found: simple_cube.step")

        result = bpy.ops.import_scene.step(filepath=path)
        self.assertEqual(result, {"FINISHED"})

        mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        self.assertGreater(len(mesh_objects), 0)

    def test_imported_meshes_have_geometry(self):
        """Every imported mesh must have vertices and faces."""
        path = _fixture("simple_cube.step")
        if not os.path.exists(path):
            self.skipTest("Fixture not found: simple_cube.step")

        bpy.ops.import_scene.step(filepath=path)

        for obj in bpy.context.scene.objects:
            if obj.type == "MESH":
                self.assertGreater(len(obj.data.vertices), 0, f"{obj.name}: no vertices")
                self.assertGreater(len(obj.data.polygons), 0, f"{obj.name}: no faces")

    def test_multi_body_step_imports_all_bodies(self):
        """A multi-body STEP file should produce one mesh object per body."""
        path = _fixture("multi_body.step")
        if not os.path.exists(path):
            self.skipTest("Fixture not found: multi_body.step")

        bpy.ops.import_scene.step(filepath=path)

        mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        self.assertGreater(len(mesh_objects), 1, "Expected multiple mesh objects for a multi-body file")


if __name__ == "__main__":
    unittest.main()
