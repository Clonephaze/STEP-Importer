#!/usr/bin/env python3
"""
Inspect the GLB that cascadio produces from a STEP/IGES file.

Prints the node hierarchy, mesh names, and material names embedded in the
GLB JSON chunk — without involving Blender at all.

Usage:
    python inspect_glb.py path/to/file.step
    python inspect_glb.py path/to/file.step --save-glb   # also writes a .glb next to the script
"""
import argparse
import json
import struct
import sys


def load_glb_json(glb_bytes: bytes) -> dict:
    """Parse the JSON chunk from a GLB binary and return it as a dict."""
    # GLB header: magic(4) + version(4) + length(4) = 12 bytes
    # First chunk: chunk_length(4) + chunk_type(4) + data
    magic, version, _ = struct.unpack_from("<III", glb_bytes, 0)
    if magic != 0x46546C67:  # "glTF"
        raise ValueError("Not a valid GLB file (bad magic bytes)")

    chunk_len, chunk_type = struct.unpack_from("<II", glb_bytes, 12)
    if chunk_type != 0x4E4F534A:  # "JSON"
        raise ValueError("First GLB chunk is not JSON")

    json_bytes = glb_bytes[20 : 20 + chunk_len]
    return json.loads(json_bytes)


def print_node_tree(gltf: dict) -> None:
    nodes    = gltf.get("nodes", [])
    meshes   = gltf.get("meshes", [])
    scenes   = gltf.get("scenes", [])
    mats     = gltf.get("materials", [])

    # Build child→parent map for indentation
    children_of = {i: node.get("children", []) for i, node in enumerate(nodes)}

    def print_node(idx: int, indent: int = 0) -> None:
        node = nodes[idx]
        name = node.get("name", f"<node {idx}>")
        mesh_idx = node.get("mesh")
        mesh_label = ""
        if mesh_idx is not None and mesh_idx < len(meshes):
            mesh_name = meshes[mesh_idx].get("name", f"mesh_{mesh_idx}")
            prims = meshes[mesh_idx].get("primitives", [])
            mat_labels = []
            for p in prims:
                m = p.get("material")
                if m is not None and m < len(mats):
                    mat_labels.append(mats[m].get("name", f"mat_{m}"))
            mat_str = ", ".join(mat_labels) if mat_labels else "—"
            mesh_label = f"  [mesh: {mesh_name!r}  materials: {mat_str}]"
        print(" " * (indent * 2) + f"- {name!r}{mesh_label}")
        for child in children_of.get(idx, []):
            print_node(child, indent + 1)

    print(f"\n{'='*60}")
    print(f"  Nodes: {len(nodes)}   Meshes: {len(meshes)}   Materials: {len(mats)}")
    print(f"{'='*60}")

    for scene_idx, scene in enumerate(scenes):
        scene_name = scene.get("name", f"scene_{scene_idx}")
        print(f"\nScene {scene_idx}: {scene_name!r}")
        for root in scene.get("nodes", []):
            print_node(root, indent=1)

    # Orphan nodes (not reachable from any scene root)
    all_children = {c for children in children_of.values() for c in children}
    scene_roots  = {r for s in scenes for r in s.get("nodes", [])}
    orphans = [i for i in range(len(nodes)) if i not in all_children and i not in scene_roots]
    if orphans:
        print(f"\nOrphan nodes (not in any scene):")
        for i in orphans:
            print_node(i, indent=1)


def main():
    parser = argparse.ArgumentParser(description="Inspect cascadio GLB output from a STEP file")
    parser.add_argument("filepath", help="Path to a .step / .stp / .iges / .igs file")
    parser.add_argument("--save-glb", action="store_true",
                        help="Save the raw GLB bytes next to this script as 'output.glb'")

    # When launched via `blender --background --python script.py -- <args>`,
    # sys.argv contains Blender's own flags too. Only parse what follows '--'.
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)

    try:
        import cascadio
    except ImportError:
        print("ERROR: cascadio is not importable from this Python environment.")
        print("Run this script from within Blender's Python, or install cascadio first.")
        sys.exit(1)

    ext = args.filepath.rsplit(".", 1)[-1].lower()
    file_type = "iges" if ext in ("iges", "igs") else "step"

    print(f"Loading {args.filepath!r} as {file_type.upper()} …")
    with open(args.filepath, "rb") as f:
        data = f.read()

    glb_bytes = cascadio.load(data, file_type=file_type)
    print(f"cascadio produced {len(glb_bytes):,} bytes of GLB")

    if args.save_glb:
        out_path = "output.glb"
        with open(out_path, "wb") as f:
            f.write(glb_bytes)
        print(f"Saved GLB to {out_path!r}")

    gltf = load_glb_json(glb_bytes)
    print_node_tree(gltf)

    print(f"\n--- Raw glTF JSON keys: {list(gltf.keys())} ---")
    extras = gltf.get("extras")
    if extras:
        print(f"Scene extras: {json.dumps(extras, indent=2)}")


if __name__ == "__main__":
    main()
