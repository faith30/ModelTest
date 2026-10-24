"""Candidate asset-authoring entry point; only CLI plumbing is provided."""

import argparse
import json
from pathlib import Path


def build_assets(manifest: dict, manifest_dir: Path) -> dict:
    """Build authored resources from the manifest and available source samples."""
    raise NotImplementedError("TODO: implement asset authoring")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate animation resources")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    with manifest_path.open("r", encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    authored_assets = build_assets(manifest, manifest_path.parent)
    serialized = json.dumps(authored_assets, ensure_ascii=False, indent=2, allow_nan=False)
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
