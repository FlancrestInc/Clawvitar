#!/usr/bin/env python3

import argparse

from pi_avatar.assets import load_manifest, process_manifest


def main():
    parser = argparse.ArgumentParser(description="Process Pi Avatar spritesheets into renderer frames.")
    parser.add_argument("--source", default="source-assets", help="Directory containing source spritesheets")
    parser.add_argument("--output", default="assets", help="Directory to write processed frames")
    parser.add_argument("--manifest", default="manifest.json", help="Manifest filename or path")
    args = parser.parse_args()

    manifest_path = args.manifest
    if "/" not in manifest_path:
        manifest_path = f"{args.source}/{manifest_path}"

    process_manifest(load_manifest(manifest_path), args.source, args.output)


if __name__ == "__main__":
    main()
