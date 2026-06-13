#!/usr/bin/env python3
"""
Build step_importer extension zips, one per OS platform.

Produces in dist/:
    step_importer-<version>-windows_x64.zip
    step_importer-<version>-macos_x64.zip
    step_importer-<version>-macos_arm64.zip
    step_importer-<version>-linux_x64.zip
    step_importer-<version>-linux_arm64.zip

Each zip bundles the cp311 and cp312-abi3 cascadio wheels for that platform.
Blender's extension installer picks the compatible wheel at install time.

Usage:
    python build.py [--blender path/to/blender]
"""
import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.join(REPO_ROOT, "step_importer")
DIST_DIR = os.path.join(REPO_ROOT, "dist")


def main():
    parser = argparse.ArgumentParser(description="Build step_importer Blender extension zips")
    parser.add_argument("--blender", default="blender",
                        help="Path to Blender executable (default: 'blender' on PATH)")
    args = parser.parse_args()

    os.makedirs(DIST_DIR, exist_ok=True)

    cmd = [
        args.blender, "--command", "extension", "build",
        "--source-dir", ADDON_DIR,
        "--output-dir", DIST_DIR,
        "--split-platforms",
        "--verbose",
    ]
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()


