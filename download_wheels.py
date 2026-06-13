#!/usr/bin/env python3
"""
Fetch missing cascadio wheels into step_importer/wheels/.

Downloads a cp312-abi3 wheel for each supported platform if not already
present. Wheels are pulled from PyPI using pip's cross-platform download
flags so you don't need the target OS to be the one running this script.

Usage:
    python download_wheels.py [--force]

Options:
    --force   Re-download all wheels even if they already exist.
"""
import argparse
import glob
import os
import subprocess
import sys

WHEELS_DIR = os.path.join(os.path.dirname(__file__), "step_importer", "wheels")
PACKAGE = "cascadio"
PYTHON_VERSION = "3.12"

# (pip --platform value, human label)
PLATFORMS = [
    ("win_amd64",                    "Windows x64"),
    ("macosx_11_0_arm64",            "macOS ARM64"),
    ("macosx_11_0_x86_64",           "macOS x64"),
    ("manylinux_2_28_x86_64",        "Linux x64"),
]


def wheels_present() -> dict[str, bool]:
    """Return a dict of platform → whether a matching wheel file exists."""
    existing = glob.glob(os.path.join(WHEELS_DIR, "*.whl"))
    result = {}
    for platform, _ in PLATFORMS:
        result[platform] = any(platform in os.path.basename(f) for f in existing)
    return result


def download_wheel(platform: str) -> bool:
    cmd = [
        sys.executable, "-m", "pip", "download",
        PACKAGE,
        "--dest", WHEELS_DIR,
        "--only-binary=:all:",
        f"--python-version={PYTHON_VERSION}",
        f"--platform={platform}",
        "--abi=abi3",
    ]
    print(f"  Running: {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Fetch missing cascadio wheels")
    parser.add_argument("--force", action="store_true", help="Re-download all wheels")
    args = parser.parse_args()

    os.makedirs(WHEELS_DIR, exist_ok=True)

    present = wheels_present()
    errors = []

    for platform, label in PLATFORMS:
        if present[platform] and not args.force:
            print(f"[skip]     {label} — already present")
            continue
        print(f"[download] {label} ({platform})")
        if not download_wheel(platform):
            print(f"[ERROR]    Failed to download wheel for {label}")
            errors.append(platform)
        else:
            print(f"[ok]       {label}")

    if errors:
        print(f"\n{len(errors)} wheel(s) failed to download: {', '.join(errors)}")
        sys.exit(1)
    else:
        print("\nAll wheels ready.")


if __name__ == "__main__":
    main()
