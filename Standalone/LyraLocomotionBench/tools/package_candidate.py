"""Allowlist candidate files into a clean package. No evaluator data is copied."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"TASK_ZH.md", "INTERFACE.md", "src/controller.py", "src/build_assets.py",
            "config/animation_graph.json", "assets/authored_assets.json", "raw/manifest.json", "LICENSE-Lyra.md"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/LyraLocomotionBench-candidate.zip")
    args = parser.parse_args()
    source = (ROOT / "candidate_template").resolve()
    manifest = json.loads((source / "raw/manifest.json").read_text("utf-8"))
    names = set(REQUIRED)
    for clip in manifest["clips"]:
        if clip["pose_file"]:
            names.add("raw/" + clip["pose_file"])
    files = {}
    for name in sorted(names):
        path = (source / name).resolve()
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError(f"Missing or unsafe candidate file: {name}")
        files[name] = path.read_bytes()
    digest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    freeze = {"schema_version": 1, "files": digest,
              "excluded": ["evaluator", "reference configurations", "authored markers/curves/notifies", "past model outputs", ".git", "UE assets"],
              "hard_os_sandbox": False,
              "boundary": "This is content separation only. A model with unrestricted host filesystem access could still read the evaluator."}
    output = args.output.resolve()
    if output.is_relative_to(source):
        raise ValueError("Package output must be outside candidate_template")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 23, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
        entry = zipfile.ZipInfo("PACKAGE_MANIFEST.json", date_time=(2026, 10, 23, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, json.dumps(freeze, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(output) as archive:
        if set(archive.namelist()) != set(files) | {"PACKAGE_MANIFEST.json"}:
            raise ValueError("Package allowlist mismatch")
        for name, expected in digest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Package readback mismatch: {name}")
    output.with_suffix(".manifest.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"output": str(output), "files": len(files), "zip_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
