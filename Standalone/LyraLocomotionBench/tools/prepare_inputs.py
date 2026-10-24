"""Prepare a separate abstract benchmark from existing read-only Lyra exports.

This never launches UE, reads old model answers, or writes a source asset.
Only sampled poses and descriptive metadata enter candidate_template.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def facts_only(value):
    """Do not import the older point-annotation task's scope or grading rules."""
    if isinstance(value, dict):
        return {key: facts_only(item) for key, item in value.items()
                if key not in {"task_scope_zh", "score_interpretation_zh"}}
    if isinstance(value, list):
        return [facts_only(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("D:/ModelTest"))
    parser.add_argument("--mark-bench", type=Path, default=Path("D:/AnimationMarkBench"))
    args = parser.parse_args()
    content = args.project.resolve() / "Content"
    previous = args.mark_bench.resolve() / "private/paired_v2"
    cfg = read(previous / "export-config.json")
    exported = {x["asset"].rsplit("/", 1)[-1]: x for x in cfg["clips"]}
    source_evidence = {Path(x["source"]).name: x for x in cfg["source_assets"]}
    relative_base = Path("Characters/Heroes/Mannequin/Animations/Locomotion/Unarmed")
    specs = []
    for gait in ("Walk", "Jog"):
        for direction in ("Fwd", "Bwd", "Left", "Right"):
            for action, suffix in (("cycle", ""), ("start", "_Start"), ("stop", "_Stop"), ("pivot", "_Pivot")):
                name = f"MM_Unarmed_{gait}_{direction}{suffix}"
                if name == "MM_Unarmed_Jog_Right_Pivot":
                    name = "MM_Unarmed_Jog_Pivot_Right"
                specs.append((name, {"gait": gait.lower(), "direction": direction.lower(), "action": action}))
    for direction, sign in (("Left", 1), ("Right", -1)):
        for angle in (90, 180):
            specs.append((f"MM_Unarmed_Turn{direction}_{angle}",
                          {"gait": None, "direction": direction.lower(), "action": "turn", "anatomical_turn_degrees": sign * angle}))
    specs.append(("MM_Unarmed_Idle_Ready", {"gait": None, "direction": None, "action": "idle"}))
    rows, audit = [], []
    raw = ROOT / "candidate_template/raw"
    for number, (name, semantic) in enumerate(specs, 1):
        source = content / relative_base / (name + ".uasset")
        if not source.is_file():
            raise FileNotFoundError(source)
        source_hash = sha(source)
        row = {"clip_id": f"motion_{number:02d}", "source_name": name, "semantic": semantic,
               "duration_seconds": None, "pose_file": None, "sample_rate_hz": None,
               "pose_bone_count": None, "availability": "metadata_only"}
        evidence = {"clip_id": row["clip_id"], "source": str(source), "source_sha256": source_hash,
                    "candidate_action": "retain_raw_pose_or_metadata_only; omit_authored_tracks"}
        if name in exported:
            old = exported[name]
            if source_hash != source_evidence[source.name]["sha256"]:
                raise ValueError(f"Stale source export: {source}")
            pose_path = previous / "candidate/poses" / (old["clip_id"] + ".json")
            pose = read(pose_path)
            # Explicit allowlist excludes curve/marker/notify/reference/source metadata.
            clean = {"schema_version": 1, "clip_id": row["clip_id"],
                     "duration": pose["duration"], "sample_rate": pose["sample_rate"],
                     "coordinate_system": pose["coordinate_system"], "rotation_format": pose["rotation_format"],
                     "bones": pose["bones"], "frames": pose["frames"]}
            if any(set(f) != {"time", "positions", "rotations_xyzw"} for f in clean["frames"]):
                raise ValueError(f"Unexpected source frame fields: {pose_path}")
            destination = raw / "poses" / (row["clip_id"] + ".json")
            save(destination, clean)
            row.update(duration_seconds=pose["duration"], pose_file="poses/" + destination.name,
                       sample_rate_hz=pose["sample_rate"], pose_bone_count=len(pose["bones"]), availability="pose_samples")
            evidence.update(source_pose=str(pose_path), source_pose_sha256=sha(pose_path), candidate_pose_sha256=sha(destination))
        rows.append(row)
        audit.append(evidence)
    manifest = {"schema_version": 1, "task_kind": "static_animation_development_artifacts",
                "coordinate_system": {"units": "cm", "up": "Z", "source_forward": "+Y", "source_left": "+X",
                    "runtime_actor_forward": "+X", "runtime_actor_left": "-Y",
                    "note": "Source mesh axes differ from the abstract actor axes. Declare the basis conversion; do not apply root displacement twice."},
                "pose_format": {"space": "component", "rotation": "xyzw", "bone_subset": True,
                    "source_sampling": "Existing RAW animation export retargeted to Manny; root motion included in pose; no AnimBP, IK or gameplay evaluation."},
                "missing_samples_policy": "metadata_only clips require generic reusable processing recipes and deferred_missing_samples status, not fabricated curves or timestamps. Input absence is not a candidate defect.",
                "clips": rows}
    save(raw / "manifest.json", manifest)
    context_root = args.mark_bench / "private/locomotion_context"
    context = read(context_root / "candidate_context.json")
    old_exports = read(context_root / "raw/export-manifest.json")
    bp_audit = []
    for entry in old_exports["exports"]:
        source = Path(entry["source"])
        output = Path(entry["output"])
        if sha(source) != entry["after_sha256"] or sha(output) != entry["output_sha256"]:
            raise ValueError(f"Stale blueprint evidence: {source}")
        bp_audit.append({"source": str(source), "source_sha256": sha(source),
                         "readonly_export": str(output), "export_sha256": sha(output)})
    save(ROOT / "evaluator/local_lyra_facts.json", {
        "schema_version": 1, "audience": "evaluator_only", "status": "bounded_static_evidence_not_executed_graph",
        "source_context": str(context_root / "candidate_context.json"), "context_sha256": sha(context_root / "candidate_context.json"),
        "context_reuse_policy": "Consumer facts only; older annotation-task exclusions and original-author matching scores are not this benchmark's rules. Some recorded facts concern out-of-scope airborne behavior; rubric.json defines applicability.",
        "blueprint_structure": facts_only(context["blueprint_structure"]),
        "annotation_targets": facts_only(context["annotation_targets"]),
        "other_animation_data": facts_only(context["other_animation_data"]),
        "limitations": [
            "No original authored marker timestamps, curve samples or modifier algorithms are included in this facts file.",
            "A saved Start-to-Cycle editor node retains an unconnected transition diagnostic; it cannot prove that transition runs.",
            "No engine synchronization, blending, collision or audio execution was verified. This benchmark grades static development details, not original-author annotation similarity."],
        "parse_boundary": context["additional_parse_boundary_zh"]})
    report = {"schema_version": 1, "status": "source_inventory_verified", "source_asset_writes": False,
              "ue_started": False, "model_calls": False, "scoring_kind": "static_evidence_review",
              "clips": audit, "blueprint_evidence": bp_audit,
              "summary": {"catalog_clips": len(rows), "pose_sampled_clips": sum(r["pose_file"] is not None for r in rows),
                          "metadata_only_clips": sum(r["pose_file"] is None for r in rows)},
              "limits": ["No engine execution, skeletal rendering, graph execution or runtime quality validated.",
                         "Current source hashes match the previous exports. Previous export correctness remains bounded by their recorded coverage."]}
    # Re-read source bytes after preparation. Existing UE projects are never mutated.
    if not all(sha(Path(x["source"])) == x["source_sha256"] for x in audit + bp_audit):
        raise ValueError("Source changed during preparation")
    save(ROOT / "evaluator/source-audit.json", report)
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
