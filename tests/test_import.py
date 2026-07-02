"""Integration tests for the STEP import pipeline.

Requires a real Blender environment with cascadio wheels installed.
Run via:
    blender --background --python tests/run_tests.py
"""
import os
import unittest

import addon_utils
import bpy

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "Resources")

BIM_EXAMPLE = os.path.join(RESOURCES_DIR, "BIMExample.step")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


def _reset_scene():
    """Reset to an empty scene and re-enable the add-on.

    ``read_factory_settings`` disables every non-factory add-on
    (including step_importer), so the import_scene.step operator and
    the addon's preferences entry would otherwise disappear after the
    first reset in a test run. ``addon_utils.enable`` (rather than
    calling ``step_importer.register()`` directly) also populates
    ``bpy.context.preferences.addons``, which the importer relies on.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("step_importer", default_set=True)


def _mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


class TestBasicImport(unittest.TestCase):
    def setUp(self):
        _reset_scene()

    def test_import_creates_mesh_objects(self):
        """Importing a STEP fixture produces at least one mesh object."""
        path = _fixture("simple_cube.step")
        if not os.path.exists(path):
            self.skipTest("Fixture not found: simple_cube.step")

        result = bpy.ops.import_scene.step(filepath=path)
        self.assertEqual(result, {"FINISHED"})
        self.assertGreater(len(_mesh_objects()), 0)

    def test_imported_meshes_have_geometry(self):
        """Every imported mesh must have vertices and faces."""
        path = _fixture("simple_cube.step")
        if not os.path.exists(path):
            self.skipTest("Fixture not found: simple_cube.step")

        bpy.ops.import_scene.step(filepath=path)

        for obj in _mesh_objects():
            self.assertGreater(len(obj.data.vertices), 0, f"{obj.name}: no vertices")
            self.assertGreater(len(obj.data.polygons), 0, f"{obj.name}: no faces")


class TestBIMExample(unittest.TestCase):
    """Tests using the BIMExample.step fixture in tests/Resources/."""

    def setUp(self):
        _reset_scene()
        if not os.path.exists(BIM_EXAMPLE):
            self.skipTest("BIMExample.step not found in tests/Resources/")

    def test_multi_body_produces_multiple_meshes(self):
        """BIMExample has many bodies — expect more than one mesh object."""
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE)
        self.assertGreater(len(_mesh_objects()), 1)

    def test_all_meshes_have_geometry(self):
        """Every imported mesh must have vertices, and at least some must have faces.

        Real BIM STEP exports mix solid bodies with 2D/annotation helper
        curves (arcs, rectangles, hatches, blocks, etc. — an effectively
        open-ended set of names), which legitimately have vertices but no
        faces. Rather than whack-a-mole every construction-geometry name,
        this checks that no mesh is entirely empty and that real solid
        geometry actually made it through the pipeline.
        """
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE)
        meshes = _mesh_objects()
        faced_count = 0
        for obj in meshes:
            self.assertGreater(len(obj.data.vertices), 0, f"{obj.name}: no vertices")
            if len(obj.data.polygons) > 0:
                faced_count += 1
        self.assertGreater(faced_count, 0, "no imported mesh has any faces")

    def test_skip_axes_removes_axis_objects(self):
        """Importing with skip_axes=True should leave no object named 'Axes*'."""
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE, skip_axes=True)
        axes_objects = [
            obj for obj in bpy.context.scene.objects
            if obj.name.lower().startswith("axes") or obj.name.lower().startswith("axis")
        ]
        self.assertEqual(axes_objects, [], f"Axis objects were not removed: {[o.name for o in axes_objects]}")

    def test_skip_axes_off_keeps_axis_objects(self):
        """Importing with skip_axes=False should leave axis objects present."""
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE, skip_axes=False)
        axes_objects = [
            obj for obj in bpy.context.scene.objects
            if obj.name.lower().startswith("axes") or obj.name.lower().startswith("axis")
        ]
        self.assertGreater(len(axes_objects), 0, "Expected axis objects to be present when skip_axes=False")

    def test_skip_filters_reduce_object_count(self):
        """Enabling all skip filters should produce fewer objects than importing everything."""
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE,
                                   skip_axes=False, skip_sketches=False, skip_lines=False,
                                   skip_hatches=False)
        count_unfiltered = len(bpy.context.scene.objects)

        _reset_scene()
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE,
                                   skip_axes=True, skip_sketches=True, skip_lines=True,
                                   skip_hatches=True, skip_wires=True, skip_rectangles=True,
                                   skip_extrudes=True, skip_cuts=True, skip_terrain=True,
                                   skip_wall_traces=True)
        count_filtered = len(bpy.context.scene.objects)

        self.assertLess(count_filtered, count_unfiltered,
                        "Enabling all filters should produce fewer objects")

    def test_merge_objects_produces_single_mesh(self):
        """merge_objects=True should join all bodies into exactly one mesh."""
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE, merge_objects=True)
        self.assertEqual(len(_mesh_objects()), 1, "Expected exactly one merged mesh object")

    def test_up_axis_y_vs_z_changes_orientation(self):
        """up_axis=Y and up_axis=Z should produce objects at different world Z positions."""
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE, up_axis="Y")
        z_y = max(obj.matrix_world.translation.z for obj in _mesh_objects()) if _mesh_objects() else 0

        _reset_scene()
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE, up_axis="Z")
        z_z = max(obj.matrix_world.translation.z for obj in _mesh_objects()) if _mesh_objects() else 0

        self.assertNotAlmostEqual(z_y, z_z, places=2,
                                  msg="up_axis=Y and up_axis=Z produced identical Z positions — correction may not be working")

    def test_materials_imported_when_enabled(self):
        """With import_materials on, at least some meshes should have material slots."""
        # Set preference then import
        prefs = bpy.context.preferences.addons.get("step_importer")
        if prefs:
            prefs.preferences.import_materials = True
        bpy.ops.import_scene.step(filepath=BIM_EXAMPLE)
        meshes_with_materials = [
            obj for obj in _mesh_objects() if len(obj.material_slots) > 0
        ]
        self.assertGreater(len(meshes_with_materials), 0,
                           "Expected at least some meshes to have materials")


if __name__ == "__main__":
    unittest.main()
