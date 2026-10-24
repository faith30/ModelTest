"""Read back the candidate package and record benchmark preparation evidence."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text("utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rubric = read(ROOT / "evaluator/rubric.json")
    assert len(rubric["items"]) == 40
    assert sum(item["weight"] for item in rubric["items"]) == 100
    raw = read(ROOT / "candidate_template/raw/manifest.json")
    assert len(raw["clips"]) == 37
    sampled = [row for row in raw["clips"] if row["availability"] == "pose_samples"]
    assert len(sampled) == 15
    for row in raw["clips"]:
        if row["availability"] == "metadata_only":
            assert row["pose_file"] is None and row["duration_seconds"] is None
    graph = read(ROOT / "candidate_template/config/animation_graph.json")
    assets = read(ROOT / "candidate_template/assets/authored_assets.json")
    assert graph["status"] == assets["status"] == "template"
    assert not graph["nodes"] and not graph["sync_groups"] and not assets["assets"]
    package = ROOT / "dist/LyraLocomotionBench-candidate.zip"
    with zipfile.ZipFile(package) as archive:
        packaged = json.loads(archive.read("PACKAGE_MANIFEST.json"))
        assert len(archive.namelist()) == len(packaged["files"]) + 1
        assert not any(name.startswith(("evaluator/", "private/", "runs/", ".git/")) or name.endswith(".uasset")
                       for name in archive.namelist())
        for name, expected in packaged["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
            assert sha(ROOT / "candidate_template" / name) == expected
    for row in sampled:
        pose = read(ROOT / "candidate_template/raw" / row["pose_file"])
        assert len(pose["bones"]) == 26
        assert pose["clip_id"] == row["clip_id"]
        assert set(pose) == {"schema_version", "clip_id", "duration", "sample_rate", "coordinate_system", "rotation_format", "bones", "frames"}
        assert all(set(frame) == {"time", "positions", "rotations_xyzw"} for frame in pose["frames"])
        assert pose["frames"][0]["time"] == 0
        assert abs(pose["frames"][-1]["time"] - row["duration_seconds"]) < 1e-6
    source_audit = read(ROOT / "evaluator/source-audit.json")
    for row in source_audit["clips"] + source_audit["blueprint_evidence"]:
        assert sha(Path(row["source"])) == row["source_sha256"]
    local_facts = read(ROOT / "evaluator/local_lyra_facts.json")
    assert not any("task_scope_zh" in row for row in local_facts["other_animation_data"])
    smoke = read(ROOT / "reports/scorer-smoke-result.json")
    assert smoke["status"] == "incomplete_review" and smoke["final_score"] is None
    assert smoke["coverage"]["reviewed_items"] == 0
    assert smoke["rubric_sha256"] == sha(ROOT / "evaluator/rubric.json")
    result = {"schema_version": 1, "status": "prepared_not_run", "checks": "passed",
              "rubric_items": 40, "max_points": 100, "candidate_catalog": 37,
              "sampled_clips": 15, "metadata_only_clips": 22,
              "candidate_files": len(packaged["files"]),
              "candidate_zip_sha256": sha(package), "rubric_sha256": sha(ROOT / "evaluator/rubric.json"),
              "source_audit_sha256": sha(ROOT / "evaluator/source-audit.json"),
              "source_asset_hashes_unchanged": True, "candidate_package_allowlist_readback": "passed",
              "review_smoke": {"status": "incomplete_review", "final_score": None},
              "model_runs": [], "model_scores": [], "ue_execution": "not_run_by_design",
              "boundary": "Readback validates package/integrity/empty-review behavior, not candidate animation semantics. Unit-test results are recorded separately."}
    output = ROOT / "evaluator/benchmark-freeze.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
