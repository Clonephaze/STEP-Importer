#!/usr/bin/env python3
"""
Download cascadio and trimesh wheels into step_importer/wheels/.

Usage:
    python download_wheels.py [--python-version 3.12]

The default Python version matches Blender 5.1+'s bundled interpreter.
"""
import argparse
import os
import subprocess
import sys

WHEELS_DIR = os.path.join(os.path.dirname(__file__), "step_importer", "wheels")


def main():
    parser = argparse.ArgumentParser(description="Download addon dependency wheels")
    parser.add_argument(
        "--python-version",
        default="3.11",
        help="Target Python version (default: 3.11 for Blender 4.2+)",
    )
    args = parser.parse_args()

    os.makedirs(WHEELS_DIR, exist_ok=True)

    cmd = [
        sys.executable, "-m", "pip", "download",
        "cascadio",
        "--dest", WHEELS_DIR,
        "--only-binary=:all:",
        f"--python-version={args.python_version}",
    ]

    print(f"Downloading wheels to: {WHEELS_DIR}")
    print(f"Command: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
