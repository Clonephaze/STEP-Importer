# Blender STEP Importer Addon — Handoff

## What this is
A Blender 5.1+ addon that imports STEP and IGES files using cascadio (OpenCASCADE-based Python wheel). No system OCCT install required — everything is bundled.

## cascadio — what it is
- GitHub: https://github.com/trimesh/cascadio
- Converts STEP/IGES files to GLB entirely in memory
- Primary API: `cascadio.load(bytes, file_type="step") -> bytes`
- Returns GLB bytes, no temp files, no disk I/O
- Also ships typed BREP primitive dataclasses and material dataclasses (PhysicalMaterial, VisualMaterial)

## Key cascadio API
```python
import cascadio
import trimesh
import io

# Convert STEP bytes to GLB bytes (no files)
glb = cascadio.load(step_bytes, file_type="step")

# Load GLB into trimesh scene
scene = trimesh.load(io.BytesIO(glb), file_type="glb")
# scene.geometry = {name: trimesh.Trimesh, ...}

# Optional: extract material info
glb = cascadio.load(step_bytes, include_materials=True)
materials = cascadio.parse_materials(mesh.metadata["cascadio"]["materials"])
# -> [PhysicalMaterial(name='Steel', density=0.00785, ...) | VisualMaterial(...)]

# Optional: BREP analytical surfaces
glb = cascadio.load(step_bytes, include_brep=True)
primitives = cascadio.primitives.parse_brep_faces(mesh.metadata["cascadio"]["brep_faces"])
# -> [Plane | Cylinder | Cone | Sphere | Torus | None, ...]
```

## Wheel situation
- cascadio builds ABI3 wheels (cp312-abi3) — compatible with Python 3.12+
- Blender 4.x ships Python 3.11, Blender 4.2+ ships 3.11/3.12
- Check PyPI for current platforms: https://pypi.org/project/cascadio/#files
- Platforms: Linux x64, Windows x64, macOS x64+ARM
- trimesh is also needed (pure Python, easy to bundle)

## Blender addon skeleton
```python
import bpy
import io
import os
import sys

# Add bundled wheels to path
ADDON_DIR = os.path.dirname(__file__)
WHEELS_DIR = os.path.join(ADDON_DIR, "wheels")
if WHEELS_DIR not in sys.path:
    sys.path.insert(0, WHEELS_DIR)

import cascadio
import trimesh

def import_step(filepath):
    step_bytes = open(filepath, "rb").read()
    ext = os.path.splitext(filepath)[1].lower()
    file_type = "iges" if ext in (".igs", ".iges") else "step"
    
    glb_bytes = cascadio.load(step_bytes, file_type=file_type, include_materials=True)
    scene = trimesh.load(io.BytesIO(glb_bytes), file_type="glb")
    
    for name, mesh in scene.geometry.items():
        me = bpy.data.meshes.new(name)
        me.from_pydata(mesh.vertices.tolist(), [], mesh.faces.tolist())
        me.update()
        ob = bpy.data.objects.new(name, me)
        bpy.context.collection.objects.link(ob)
```

## Bundling wheels
Drop platform wheels into `addon/wheels/` and install with:
```
pip download cascadio trimesh --dest addon/wheels/ --only-binary=:all: --python-version 3.11
```
Or manually place the .whl files and use zipimport / sys.path injection.

## Things to handle in the addon
- Multi-body STEP files (scene.geometry has multiple meshes)
- Materials → Blender material slots (colors from VisualMaterial.base_color)
- Scale: cascadio outputs meters, Blender uses meters natively — should match
- ABI3 wheel is cp312-abi3, test against Blender's exact Python version
- trimesh has many optional deps — only core is needed, watch bundle size

## Known issues / future PRs in cascadio
- Non-ASCII part names (Chinese etc.) come through as '??' — bug in OCCT's
  TCollection_AsciiString(ExtendedString) conversion in RWMesh.cxx
  Fix: use ToUTF8CString instead. Test file: NonStandardCharacters.step with 嘿呀
- Encoding PR not yet submitted, separate branch needed

## cascadio fork location
C:\Users\Jack\Documents\My Projects\High Level Scripts\cascadio
Branch: feature/material-info-dataclasses (PR submitted to trimesh/cascadio)

the easiest way to parse GLB into vertices/faces in Python. But in a Blender addon you have a much simpler option — Blender already has a built-in GLB importer:

```python
import tempfile, os

def import_step(filepath):
    step_bytes = open(filepath, "rb").read()
    glb_bytes = cascadio.load(step_bytes, file_type="step")
    
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        f.write(glb_bytes)
        tmp = f.name
    
    bpy.ops.import_scene.gltf(filepath=tmp)
    os.unlink(tmp)
```
