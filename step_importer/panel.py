import os
import traceback
from math import radians

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

from .importer import regenerate_parts
from .preferences import QUALITY_PRESET_ITEMS, QUALITY_PRESETS
from .utils import cascadio_available, cleanup_topology, get_addon_preferences


# ---------------------------------------------------------------------------
# Session-persistent tessellation settings for the Regenerate panel
# ---------------------------------------------------------------------------

def _update_regen_preset(self, context):
    if self.tol_preset in QUALITY_PRESETS:
        linear, angular = QUALITY_PRESETS[self.tol_preset]
        self.tol_linear = linear
        self.tol_angular = angular


class STEP_RegenSettings(PropertyGroup):
    tol_preset: EnumProperty(
        name="Quality Preset",
        description="Tessellation quality; higher quality produces smoother curves with more triangles",
        items=QUALITY_PRESET_ITEMS,
        default="BALANCED",
        update=_update_regen_preset,
    )
    tol_linear: FloatProperty(
        name="Linear Tolerance",
        description="Maximum distance between the mesh and the true CAD surface",
        default=0.01,
        min=0.0001,
    )
    tol_angular: FloatProperty(
        name="Angular Tolerance",
        description="Maximum angle between adjacent triangles in radians",
        default=0.5,
        min=0.001,
    )
    tol_relative: BoolProperty(
        name="Relative Tolerance",
        description="Scale linear tolerance to each feature size rather than using a fixed world-space distance",
        default=True,
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class STEP_OT_regenerate_part(Operator):
    bl_idname = "step.regenerate_part"
    bl_label = "Regenerate Part"
    bl_description = "Re-tessellate this part from the original STEP file with new quality settings"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not cascadio_available():
            return False
        return any(
            obj.type == "MESH"
            and "step_source_file" in obj
            and "step_node_path" in obj
            and obj["step_node_path"] != "__merged__"
            for obj in context.selected_objects or []
        )

    def execute(self, context):
        regen = context.window_manager.step_regen

        if regen.tol_preset in QUALITY_PRESETS:
            tol_linear, tol_angular = QUALITY_PRESETS[regen.tol_preset]
        else:
            tol_linear = regen.tol_linear
            tol_angular = regen.tol_angular

        prefs = get_addon_preferences(context)

        try:
            count, errors = regenerate_parts(
                context.selected_objects or [],
                tol_linear=tol_linear,
                tol_angular=tol_angular,
                tol_relative=regen.tol_relative,
                import_materials=prefs.import_materials,
            )
        except Exception as e:
            traceback.print_exc()
            self.report({"ERROR"}, f"Regenerate failed: {e}")
            return {"CANCELLED"}

        for err in errors:
            self.report({"WARNING"}, err)

        if count > 0:
            noun = "part" if count == 1 else "parts"
            self.report({"INFO"}, f"Regenerated {count} {noun}")
            return {"FINISHED"}
        return {"CANCELLED"}


class STEP_OT_cleanup_selected(Operator):
    bl_idname = "step.cleanup_selected"
    bl_label = "Clean Up Topology"
    bl_description = "Run topology cleanup on all selected mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects or [])

    def execute(self, context):
        prefs = get_addon_preferences(context)
        mesh_objects = [obj for obj in context.selected_objects or [] if obj.type == "MESH"]

        # bmesh cannot access a mesh that is in edit mode; switch to Object
        # mode first and restore afterward.
        original_mode = context.object.mode if context.object else "OBJECT"
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            cleanup_topology(
                mesh_objects,
                remove_doubles=prefs.ct_doubles,
                doubles_dist=prefs.ct_doubles_dist,
                dissolve=prefs.ct_dissolve,
                dissolve_angle=prefs.ct_dissolve_angle,
                temp_sharp=not prefs.shade_smooth,
            )
            if prefs.shade_smooth:
                for obj in mesh_objects:
                    bpy.context.view_layer.objects.active = obj
                    obj.select_set(True)
                    bpy.ops.object.shade_smooth_by_angle(angle=radians(30))
        finally:
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)

        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class STEP_PT_tools(Panel):
    bl_label = "STEP Tools"
    bl_idname = "STEP_PT_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "STEP"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        obj = context.active_object

        # Regenerate section
        box = layout.box()
        box.label(text="Regenerate Part", icon="FILE_REFRESH")

        is_step_obj = (
            obj is not None
            and "step_source_file" in obj
            and "step_node_path" in obj
            and obj["step_node_path"] != "__merged__"
        )

        eligible_selected = [
            o for o in context.selected_objects or []
            if o.type == "MESH"
            and "step_source_file" in o
            and o.get("step_node_path", "__merged__") != "__merged__"
        ]
        eligible_count = len(eligible_selected)

        if eligible_count > 1:
            col = box.column(align=True)
            col.label(text=f"{eligible_count} STEP parts selected", icon="OBJECT_DATA")
        elif obj is not None and is_step_obj:
            col = box.column(align=True)
            col.label(text=obj["step_node_path"], icon="OBJECT_DATA")
            col.label(text=os.path.basename(obj["step_source_file"]), icon="FILE")
        else:
            if obj is not None and obj.get("step_node_path") == "__merged__":
                box.label(text="Merged objects cannot be regenerated", icon="INFO")
            else:
                box.label(text="Select an imported STEP object", icon="INFO")

        regen = context.window_manager.step_regen
        col = box.column(align=True)
        col.prop(regen, "tol_preset")
        if regen.tol_preset == "CUSTOM":
            col.prop(regen, "tol_linear")
            col.prop(regen, "tol_angular")
        col.prop(regen, "tol_relative")

        btn_text = f"Regenerate {eligible_count} Parts" if eligible_count > 1 else "Regenerate Part"
        row = box.row()
        row.enabled = eligible_count > 0
        row.operator("step.regenerate_part", icon="FILE_REFRESH", text=btn_text)

        layout.separator()

        # Cleanup section
        box = layout.box()
        box.label(text="Cleanup", icon="BRUSH_DATA")

        prefs = get_addon_preferences(context)
        col = box.column(align=True)
        col.prop(prefs, "shade_smooth")
        col.prop(prefs, "ct_doubles")
        if prefs.ct_doubles:
            col.prop(prefs, "ct_doubles_dist")
        col.prop(prefs, "ct_dissolve")
        if prefs.ct_dissolve:
            col.prop(prefs, "ct_dissolve_angle")

        box.operator("step.cleanup_selected", icon="MESH_DATA")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_CLASSES = [
    STEP_RegenSettings,
    STEP_OT_regenerate_part,
    STEP_OT_cleanup_selected,
    STEP_PT_tools,
]


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.step_regen = PointerProperty(type=STEP_RegenSettings)


def unregister():
    del bpy.types.WindowManager.step_regen
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
