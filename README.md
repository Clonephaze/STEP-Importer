## .STEP Importer

A straightforward STEP import addon that allows you to directly select or drag-and-drop `.step` and `.stp` files into Blender without requiring external conversion tools or CAD software.

### Features

* Choose the import "Up" direction.
* Rotate imported objects in quarter-turn increments.
* Filter out non-solid STEP entities such as sketches and construction history.
* Basic material support.
* Drag and drop one or more STEP files directly into Blender.
* Uses Blender's built-in glTF importer for mesh and material creation.

### Core Conversion Logic

This addon uses the Python library Cascadio to perform all STEP-to-mesh conversion. Cascadio converts STEP geometry into glTF data, which is then passed directly to Blender's built-in glTF importer. Mesh generation, object creation, and material assignment are therefore handled through Blender's existing glTF import pipeline.


### FAQ

#### The geometry looks messy after import. Can this be improved?

Unfortunately, as of now, no. This addon does not perform any geometry conversion itself. All tessellation and mesh generation are handled by Cascadio. Improvements made upstream in Cascadio will automatically benefit this addon when updated.

Automatic and/or manual post-import mesh cleanup is being investigated and *should* be added in a future update.

#### Can I export STEP files as well?

No. STEP files store precise CAD geometry (B-Rep/NURBS surfaces), while Blender primarily works with polygon meshes. Once CAD data has been converted into triangles, the information required to recreate an accurate STEP model is no longer available. As a result, STEP export is outside the scope of this addon.
