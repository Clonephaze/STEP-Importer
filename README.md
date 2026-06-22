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

#### The exact naming structure from my CAD assembly doesn’t match what appears in Blender. Why?
Currently this is a limitation of cascadio, but it is one I have already identified and am 90 percent sure I can fix it with a simple PR upstream, if they accept the change. 
When the fix has been pushed upstream, this addon will automatically benefit and I will push an update to support it. 

#### Non-standard characters import incorrectly. Do you plan to support them?

Yes, this one is actually a limitation of OCCT itself but one that I feel they will be happy to accept a fix for and I already know how to fix it.
I doubt they would deny this fix, as theres no downside to accepting these characters. As soon as the fix is accepted upstream I will push a fix for it here
