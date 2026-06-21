import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, EnumProperty

_AXIS_ITEMS = [
    ("X", "X", ""),
    ("Y", "Y", ""),
    ("Z", "Z", ""),
    ("MINUS_X", "-X", ""),
    ("MINUS_Y", "-Y", ""),
    ("MINUS_Z", "-Z", ""),
]


_ROTATION_ITEMS = [
    ("-90", "-90°", "Rotate 90° counter-clockwise"),
    ("0", "0°", "No rotation"),
    ("90", "90°", "Rotate 90° clockwise"),
    ("180", "180°", "Rotate 180°"),
]


class STEPImporterPreferences(AddonPreferences):
    bl_idname = __package__

    import_materials: BoolProperty(
        name="Import Materials",
        description="Apply material colors from STEP file when available",
        default=True,
    )

    default_up_axis: EnumProperty(
        name="Source Up Axis",
        description="Which axis was 'up' in the application that exported the file (Y = glTF/FreeCAD/most CAD, Z = some CAD tools)",
        items=_AXIS_ITEMS,
        default="Y",
    )

    default_rotation: EnumProperty(
        name="Default Rotation",
        description="Default rotation around the vertical axis after up-axis correction",
        items=_ROTATION_ITEMS,
        default="0",
    )

    tol_linear: bpy.props.FloatProperty(
        name="Linear Tolerance",
        description="Maximum distance between the mesh and the true CAD surface. In relative mode, expressed as a fraction of each edge's length. Lower values produce smoother geometry with more triangles.",
        default=0.01,
        min=0.001,
    )

    tol_angular: bpy.props.FloatProperty(
        name="Angular Tolerance",
        description="Maximum angle between adjacent triangles in radians. Controls curve smoothness independent of part size — lower values keep curves smooth on both large and small features.",
        default=0.5,
        min=0.001,
    )

    tol_relative: BoolProperty(
        name="Relative Tolerance",
        description="When True, scale linear tolerance to each feature's size rather than using a fixed world-space distance. Recommended for assemblies with mixed part sizes.",
        default=True,
    )
    
    shade_smooth: BoolProperty(
        name="Shade Smooth",
        description="Automatically shade smooth imported meshes.",
        default=True,
    )

    cleanup_topology: BoolProperty(
        name="Clean Up Topology",
        description="Cleanup of imported topology (remove doubles, merge nearby vertices, etc). May increase import time but can help with messy STEP files.",
        default=False,
    )

    ct_doubles: BoolProperty(
        name="Remove Doubles",
        description="Remove duplicate vertices that are very close together.",
        default=True,
    )

    ct_doubles_dist: bpy.props.FloatProperty(
        name="Doubles Distance",
        description="Distance threshold for removing duplicate vertices.",
        precision=5,
        default=0.0001,
        min=0.00001,
        max=1.0,
    )

    ct_dissolve: BoolProperty(
        name="Dissolve Faces",
        description="Dissolve coplanar faces to simplify the mesh.",
        default=True,
    )

    ct_dissolve_angle: bpy.props.FloatProperty(
        name="Dissolve Angle",
        description="Angle threshold (in degrees) for dissolving coplanar faces.",
        default=0.5,
        min=0.1,
        max=180.0,
    )

    show_progress: BoolProperty(
        name="Show Import Progress",
        description="Display a GPU progress bar in the 3D viewport during import",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        layout.label(text="Default Transform (pre-fill for new imports)")
        layout.prop(self, "default_up_axis", text="Up in Source App")
        layout.prop(self, "default_rotation")
        layout.separator()
        
        layout.prop(self, "import_materials")
        layout.prop(self, "show_progress")
        layout.separator()

        layout.label(text="Tolerances (for cascadio conversion)")
        layout.prop(self, "tol_linear")
        layout.prop(self, "tol_angular")
        layout.prop(self, "tol_relative")
        layout.separator()

        layout.prop(self, "shade_smooth")
        layout.prop(self, "cleanup_topology")
        if self.cleanup_topology:
            layout.prop(self, "ct_doubles")
            if self.ct_doubles:
                layout.prop(self, "ct_doubles_dist")
            layout.prop(self, "ct_dissolve")
            if self.ct_dissolve:
                layout.prop(self, "ct_dissolve_angle")


def register():
    bpy.utils.register_class(STEPImporterPreferences)


def unregister():
    bpy.utils.unregister_class(STEPImporterPreferences)
