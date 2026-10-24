"""Asset authoring for the Lyra-style unarmed ground locomotion delivery.

CLI (see INTERFACE.md):
    python src/build_assets.py --manifest raw/manifest.json --output assets/authored_assets.json

What it really does for every manifest clip with ``availability == pose_samples``:
  1. loads and validates the 26-bone component-space samples,
  2. converts source basis (+Y fwd, +X left, +Z up) into actor basis (+X fwd, +Y right, +Z up),
  3. extracts the root bone track as a separate root-motion curve (translation + yaw),
  4. stores the pose re-expressed relative to the root (in-place pose, root = identity),
     so root displacement is never applied twice,
  5. derives curves/markers from the samples only (speed, distance matching curves,
     pivot time, remaining turn yaw, foot contact sync markers, loop closure error),
  6. writes one pose artefact per asset to ``assets/authored/`` and the resource table.

Clips with ``metadata_only`` get the identical recipe recorded with
``status: deferred_missing_samples`` and ``null`` data; nothing is invented for them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from anim_math import (  # noqa: E402
    qcanonical,
    qconj,
    qmul,
    qnormalize,
    qrotate,
    quat_angle_degrees,
    wrap_degrees,
    yaw_degrees_from_quat,
)

BUILDER_VERSION = "1.0.0"
ARTIFACT_DIR_NAME = "authored"

# Source -> actor basis. actor = M * source. Proper rotation (det = +1): -90 deg about +Z.
BASIS_MATRIX = [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
BASIS_QUAT = [0.0, 0.0, -math.sqrt(0.5), math.sqrt(0.5)]

FOOT_CONTACT_PARAMS = {
    "bones": {"l": ["foot_l", "ball_l"], "r": ["foot_r", "ball_r"]},
    "height_above_clip_min_cm": 5.0,
    "max_horizontal_speed_cm_s": 60.0,
    "min_contact_duration_s": 0.08,
    "speed_space": "actor component space including root motion (approximates world for flat ground)",
}
CYCLE_SPEED_EPS = 1.0
ROUND = 5


def _r(x: float) -> float:
    return round(float(x), ROUND)


def _asset_id(semantic: dict) -> str:
    action = semantic.get("action")
    if action == "turn":
        deg = semantic.get("anatomical_turn_degrees")
        side = "left" if deg is not None and deg > 0 else "right"
        return f"turn_in_place_{side}_{abs(int(deg))}"
    if action == "idle":
        return "idle_ready"
    return f"{semantic['gait']}_{semantic['direction']}_{action}"


# --------------------------------------------------------------------------- recipes

def recipe_for(semantic: dict) -> dict:
    """Reusable processing recipe; identical for ready and deferred clips of a kind."""
    action = semantic.get("action")
    steps = [
        {"op": "load_component_space_samples", "params": {"expected_bone_count": 26, "require_uniform_rate": True}},
        {"op": "validate_skeleton_against_reference_subset", "params": {"reference": "skeleton.bones"}},
        {"op": "convert_basis", "params": {"matrix_actor_from_source": BASIS_MATRIX,
                                           "rotation_premultiply_xyzw": BASIS_QUAT}},
        {"op": "extract_root_motion", "params": {"bone": "root", "channels": ["tx", "ty", "tz", "yaw"],
                                                 "origin": "first_frame", "yaw_sign": "positive turns +X toward +Y"}},
        {"op": "make_pose_root_relative", "params": {"formula": "p' = q_root^-1 (p - t_root); q' = q_root^-1 * q"}},
        {"op": "detect_foot_contacts", "params": FOOT_CONTACT_PARAMS},
    ]
    if action == "cycle":
        steps += [
            {"op": "loop_analysis", "params": {"loop_range": "[first_time, last_time]",
                                               "closure_metric": "max root-relative bone position delta first vs last"}},
            {"op": "derive_speed", "params": {"method": "horizontal root displacement / loop duration"}},
            {"op": "derive_sync_markers", "params": {"source": "foot contact onsets", "names": ["foot_l_plant", "foot_r_plant"]}},
        ]
    elif action == "start":
        steps.append({"op": "derive_distance_curve", "params": {"name": "distance_traveled_cm",
                                                                 "method": "cumulative horizontal root path length from t0"}})
    elif action == "stop":
        steps.append({"op": "derive_distance_curve", "params": {"name": "distance_to_stop_cm",
                                                                 "method": "remaining horizontal root path length to final frame"}})
    elif action == "pivot":
        steps.append({"op": "derive_pivot", "params": {"pivot_time": "frame of minimum horizontal root speed between entry and exit",
                                                        "curve": "signed_distance_to_pivot_cm (negative before pivot, positive after)",
                                                        "entry_exit_direction": "sign of root velocity along clip axis before/after pivot"}})
    elif action == "turn":
        steps.append({"op": "derive_turn_curves", "params": {"curves": ["root_yaw_deg", "remaining_turn_yaw_deg"],
                                                              "turn_end_time": "first time |remaining| <= 1 deg"}})
    elif action == "idle":
        steps.append({"op": "loop_analysis", "params": {"loop_range": "[first_time, last_time]"}})
    steps.append({"op": "write_pose_artifact", "params": {"dir": ARTIFACT_DIR_NAME, "format": "json", "precision_decimals": ROUND}})
    return {"builder": "src/build_assets.py", "builder_version": BUILDER_VERSION, "steps": steps}


# --------------------------------------------------------------------------- processing

def _load_samples(path: Path, clip: dict) -> dict:
    with path.open("r", encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    bones = doc["bones"]
    frames = doc["frames"]
    if clip.get("pose_bone_count") is not None and len(bones) != clip["pose_bone_count"]:
        raise ValueError(f"{clip['clip_id']}: bone count mismatch")
    if len(frames) < 2:
        raise ValueError(f"{clip['clip_id']}: not enough frames")
    rate = clip.get("sample_rate_hz") or doc.get("sample_rate")
    times = [float(f["time"]) for f in frames]
    for i in range(1, len(times)):
        if abs((times[i] - times[i - 1]) - 1.0 / rate) > 1e-3:
            raise ValueError(f"{clip['clip_id']}: non-uniform sampling at frame {i}")
    for f in frames:
        if len(f["positions"]) != len(bones) or len(f["rotations_xyzw"]) != len(bones):
            raise ValueError(f"{clip['clip_id']}: frame array size mismatch")
        for v in f["positions"] + f["rotations_xyzw"]:
            if not all(math.isfinite(c) for c in v):
                raise ValueError(f"{clip['clip_id']}: non-finite sample")
    return {"bones": bones, "times": times, "frames": frames, "rate": rate,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _convert(frames: list) -> list:
    out = []
    for f in frames:
        pos = [[sum(BASIS_MATRIX[r][c] * p[c] for c in range(3)) for r in range(3)] for p in f["positions"]]
        rot = [qcanonical(qnormalize(qmul(BASIS_QUAT, q))) for q in f["rotations_xyzw"]]
        out.append({"positions": pos, "rotations": rot})
    return out


def _root_relative(conv: list):
    """Split root track out; return (root_curve, in_place_frames)."""
    root0_t = conv[0]["positions"][0]
    root0_yaw = yaw_degrees_from_quat(conv[0]["rotations"][0])
    root_curve = {"tx_cm": [], "ty_cm": [], "tz_cm": [], "yaw_deg": []}
    in_place = []
    max_tilt = 0.0
    yaw_unwrapped = 0.0
    prev_yaw = root0_yaw
    for f in conv:
        t = f["positions"][0]
        q = f["rotations"][0]
        yaw = yaw_degrees_from_quat(q)
        yaw_unwrapped += wrap_degrees(yaw - prev_yaw)
        prev_yaw = yaw
        # root rotation must be pure yaw for the yaw channel to be lossless
        from anim_math import quat_from_yaw_degrees
        max_tilt = max(max_tilt, quat_angle_degrees(q, quat_from_yaw_degrees(yaw)))
        root_curve["tx_cm"].append(_r(t[0] - root0_t[0]))
        root_curve["ty_cm"].append(_r(t[1] - root0_t[1]))
        root_curve["tz_cm"].append(_r(t[2] - root0_t[2]))
        root_curve["yaw_deg"].append(_r(yaw_unwrapped))
        qinv = qconj(q)
        pos = [[_r(c) for c in qrotate(qinv, [p[0] - t[0], p[1] - t[1], p[2] - t[2]])] for p in f["positions"]]
        rot = [[_r(c) for c in qcanonical(qnormalize(qmul(qinv, r)))] for r in f["rotations"]]
        in_place.append({"positions": pos, "rotations_xyzw": rot})
    return root_curve, in_place, {"root_origin_actor_cm": [_r(c) for c in root0_t],
                                  "root_origin_yaw_deg": _r(root0_yaw),
                                  "max_root_non_yaw_rotation_deg": _r(max_tilt)}


def _horizontal_path(root_curve: dict) -> list:
    xs, ys = root_curve["tx_cm"], root_curve["ty_cm"]
    acc = [0.0]
    for i in range(1, len(xs)):
        acc.append(acc[-1] + math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]))
    return acc


def _root_speed(root_curve: dict, rate: float) -> list:
    xs, ys = root_curve["tx_cm"], root_curve["ty_cm"]
    n = len(xs)
    sp = []
    for i in range(n):
        a, b = max(0, i - 1), min(n - 1, i + 1)
        dt = (b - a) / rate
        sp.append(math.hypot(xs[b] - xs[a], ys[b] - ys[a]) / dt if dt > 0 else 0.0)
    return sp


def _foot_contacts(conv: list, bones: list, times: list, rate: float) -> dict:
    names = [b["name"] for b in bones]
    result = {}
    min_frames = max(1, int(round(FOOT_CONTACT_PARAMS["min_contact_duration_s"] * rate)))
    for side, bnames in FOOT_CONTACT_PARAMS["bones"].items():
        idx = [names.index(b) for b in bnames]
        zmin = min(min(f["positions"][i][2] for f in conv) for i in idx)
        flags = []
        n = len(conv)
        for k in range(n):
            a, b = max(0, k - 1), min(n - 1, k + 1)
            dt = (b - a) / rate
            planted = False
            for i in idx:
                pa, pb, pk = conv[a]["positions"][i], conv[b]["positions"][i], conv[k]["positions"][i]
                hs = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) / dt
                if pk[2] <= zmin + FOOT_CONTACT_PARAMS["height_above_clip_min_cm"] and \
                        hs <= FOOT_CONTACT_PARAMS["max_horizontal_speed_cm_s"]:
                    planted = True
            flags.append(planted)
        intervals = []
        k = 0
        while k < n:
            if flags[k]:
                s = k
                while k < n and flags[k]:
                    k += 1
                if k - s >= min_frames:
                    intervals.append([_r(times[s]), _r(times[k - 1])])
            else:
                k += 1
        result[side] = intervals
    return result


def _process_clip(clip: dict, samples: dict, conv: list, artifact_dir: Path, out_dir: Path) -> dict:
    sem = clip["semantic"]
    action = sem["action"]
    times = samples["times"]
    rate = samples["rate"]
    bones = samples["bones"]
    root_curve, in_place, root_info = _root_relative(conv)
    asset_id = _asset_id(sem)

    artifact = {
        "schema_version": 1,
        "asset_id": asset_id,
        "source_clip_id": clip["clip_id"],
        "source_pose_file": clip["pose_file"],
        "source_sha256": samples["sha256"],
        "space": "actor component space, root-relative (root bone = identity); root motion stored separately in authored_assets.json",
        "bones": [{"name": b["name"], "parent": b["parent"]} for b in bones],
        "sample_rate_hz": rate,
        "times": [_r(t) for t in times],
        "frames": in_place,
    }
    rel = f"{ARTIFACT_DIR_NAME}/{asset_id}.pose.json"
    text = json.dumps(artifact, separators=(",", ":"), allow_nan=False)
    (artifact_dir / f"{asset_id}.pose.json").write_text(text, encoding="utf-8")

    path_len = _horizontal_path(root_curve)
    speed = _root_speed(root_curve, rate)
    contacts = _foot_contacts(conv, bones, times, rate)
    duration = times[-1] - times[0]
    curves = {"time_s": [_r(t) for t in times], "root_speed_cm_s": [_r(s) for s in speed]}
    data = {
        "pose_artifact": rel,
        "pose_artifact_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "duration_seconds": _r(duration),
        "sample_rate_hz": rate,
        "frame_count": len(times),
        "time_origin": "source time 0 (no trimming applied)",
        "root_motion": dict(root_curve, **root_info,
                            note="Delta from frame 0, actor basis. Consumer applies either this curve OR capsule motion, never both."),
        "foot_contacts": contacts,
        "curves": curves,
    }
    end_disp = math.hypot(root_curve["tx_cm"][-1], root_curve["ty_cm"][-1])
    if end_disp > CYCLE_SPEED_EPS or path_len[-1] > CYCLE_SPEED_EPS:
        ang = math.degrees(math.atan2(root_curve["ty_cm"][-1], root_curve["tx_cm"][-1]))
        data["net_root_heading_actor_deg"] = _r(ang)
    data["net_root_displacement_cm"] = _r(end_disp)

    if action == "cycle":
        a, b = in_place[0], in_place[-1]
        closure = max(math.dist(pa, pb) for pa, pb in zip(a["positions"], b["positions"]))
        rot_closure = max(quat_angle_degrees(qa, qb) for qa, qb in zip(a["rotations_xyzw"], b["rotations_xyzw"]))
        data["loop"] = {"loop_start_s": _r(times[0]), "loop_end_s": _r(times[-1]),
                        "period_s": _r(duration),
                        "last_sample_duplicates_first": closure < 2.0 and rot_closure < 3.0,
                        "closure_max_position_error_cm": _r(closure),
                        "closure_max_rotation_error_deg": _r(rot_closure)}
        data["authored_speed_cm_s"] = _r(end_disp / duration)
        data["stride_length_cm"] = _r(end_disp)
        markers = []
        for side, ivs in contacts.items():
            for s, _e in ivs:
                markers.append({"name": f"foot_{side}_plant", "time_s": s})
        markers.sort(key=lambda m: m["time_s"])
        data["sync_markers"] = markers
        data["sync_marker_method"] = "onset of detected foot contact interval (derived, not authored notify)"
    elif action == "start":
        curves["distance_traveled_cm"] = [_r(d) for d in path_len]
        data["end_speed_cm_s"] = _r(speed[-1])
    elif action == "stop":
        total = path_len[-1]
        curves["distance_to_stop_cm"] = [_r(total - d) for d in path_len]
        rest = next((times[i] for i in range(len(times)) if total - path_len[i] < 0.5 and speed[i] < 5.0), times[-1])
        data["stop_distance_cm"] = _r(total)
        data["entry_speed_cm_s"] = _r(speed[0])
        data["root_at_rest_time_s"] = _r(rest)
    elif action == "pivot":
        n = len(times)
        lo, hi = n // 10, n - n // 10
        piv = min(range(lo, hi), key=lambda i: speed[i])
        tp = times[piv]
        dist = [_r(path_len[i] - path_len[piv]) for i in range(n)]
        curves["signed_distance_to_pivot_cm"] = dist
        def heading(i0, i1):
            dx = root_curve["tx_cm"][i1] - root_curve["tx_cm"][i0]
            dy = root_curve["ty_cm"][i1] - root_curve["ty_cm"][i0]
            return math.degrees(math.atan2(dy, dx))
        data["pivot_time_s"] = _r(tp)
        data["entry_velocity_heading_actor_deg"] = _r(heading(0, max(1, piv // 2)))
        data["exit_velocity_heading_actor_deg"] = _r(heading(min(n - 2, (piv + n) // 2), n - 1))
        data["entry_speed_cm_s"] = _r(speed[0])
        data["exit_speed_cm_s"] = _r(speed[-1])
    elif action == "turn":
        yaw = root_curve["yaw_deg"]
        total = yaw[-1]
        curves["root_yaw_deg"] = list(yaw)
        curves["remaining_turn_yaw_deg"] = [_r(total - y) for y in yaw]
        end_t = next((times[i] for i in range(len(times)) if abs(total - yaw[i]) <= 1.0), times[-1])
        data["total_root_yaw_actor_deg"] = _r(total)
        data["anatomical_turn_degrees_from_manifest"] = sem.get("anatomical_turn_degrees")
        data["turn_end_time_s"] = _r(end_t)
        data["sign_check"] = "actor yaw delta = -anatomical_turn_degrees"

    return {
        "asset_id": asset_id,
        "kind": f"locomotion_{action}" if action not in ("turn", "idle") else action,
        "semantic": sem,
        "source_clip_ids": [clip["clip_id"]],
        "source_name": clip["source_name"],
        "status": "ready",
        "recipe": recipe_for(sem),
        "data": data,
    }


def _deferred_entry(clip: dict) -> dict:
    sem = clip["semantic"]
    return {
        "asset_id": _asset_id(sem),
        "kind": f"locomotion_{sem['action']}" if sem["action"] not in ("turn", "idle") else sem["action"],
        "semantic": sem,
        "source_clip_ids": [clip["clip_id"]],
        "source_name": clip["source_name"],
        "status": "deferred_missing_samples",
        "missing_inputs": ["pose_file", "sample_rate_hz", "duration_seconds", "pose_bone_count"],
        "recipe": recipe_for(sem),
        "data": None,
        "pending_work": "Provide component-space samples in the manifest format, then rerun build_assets.py; "
                        "the same recipe will produce pose artefact, root motion and derived curves.",
    }


def _derive_ready_pose(ready_assets: dict, processed: dict) -> dict | None:
    """Static single-frame pose shared by start t0 / stop end / turn t0. Not an idle animation."""
    cands = []  # (asset_id, frame_index)
    for aid, info in processed.items():
        action = info["semantic"]["action"]
        if action in ("start", "turn"):
            cands.append((aid, 0))
        elif action == "stop":
            cands.append((aid, len(info["in_place"]) - 1))
    if not cands:
        return None
    base_id, base_idx = cands[0]
    base = processed[base_id]["in_place"][base_idx]
    checks = []
    for aid, idx in cands[1:]:
        f = processed[aid]["in_place"][idx]
        err = max(math.dist(a, b) for a, b in zip(base["positions"], f["positions"]))
        checks.append({"asset_id": aid, "frame_index": idx, "max_position_delta_cm": _r(err)})
    return {
        "asset_id": "ready_pose_static",
        "kind": "static_pose",
        "semantic": {"gait": None, "direction": None, "action": "static_ready_pose"},
        "source_clip_ids": [processed[base_id]["clip_id"]],
        "source_name": None,
        "derived_from": {"asset_id": base_id, "frame_index": base_idx},
        "status": "ready",
        "recipe": {"builder": "src/build_assets.py", "builder_version": BUILDER_VERSION,
                   "steps": [{"op": "extract_single_frame", "params": {"asset_id": base_id, "frame_index": base_idx}},
                             {"op": "cross_check_frames", "params": {"candidates": "start t0, stop last frame, turn t0"}}]},
        "data": {
            "pose_artifact": ready_assets[base_id]["data"]["pose_artifact"],
            "frame_index": base_idx,
            "duration_seconds": 0.0,
            "cross_check": checks,
            "note": "Derived static pose only. It is NOT MM_Unarmed_Idle_Ready (motion_37, deferred); no breathing/idle motion.",
        },
    }


def build_assets(manifest: dict, manifest_dir: Path, output_dir: Path | None = None) -> dict:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema_version")
    output_dir = Path(output_dir) if output_dir is not None else Path.cwd() / "assets"
    artifact_dir = output_dir / ARTIFACT_DIR_NAME
    artifact_dir.mkdir(parents=True, exist_ok=True)

    skeleton_ref = None
    assets = []
    ready = {}
    processed = {}
    seen = set()
    for clip in manifest["clips"]:
        aid = _asset_id(clip["semantic"])
        if aid in seen:
            raise ValueError(f"duplicate asset id {aid}")
        seen.add(aid)
        if clip.get("availability") == "pose_samples" and clip.get("pose_file"):
            samples = _load_samples(manifest_dir / clip["pose_file"], clip)
            bones = [(b["name"], b["parent"]) for b in samples["bones"]]
            if skeleton_ref is None:
                skeleton_ref = bones
            elif bones != skeleton_ref:
                raise ValueError(f"{clip['clip_id']}: bone hierarchy differs from reference subset")
            conv = _convert(samples["frames"])
            entry = _process_clip(clip, samples, conv, artifact_dir, output_dir)
            _, in_place, _ = _root_relative(conv)
            processed[aid] = {"semantic": clip["semantic"], "in_place": in_place, "clip_id": clip["clip_id"]}
            ready[aid] = entry
            assets.append(entry)
        else:
            assets.append(_deferred_entry(clip))

    rp = _derive_ready_pose(ready, processed)
    if rp:
        assets.append(rp)

    n_ready = sum(1 for a in assets if a["status"] == "ready")
    return {
        "schema_version": 1,
        "status": "partial_ready_with_deferred",
        "builder_version": BUILDER_VERSION,
        "source_manifest": "raw/manifest.json",
        "artifact_root": "paths in data.pose_artifact are relative to this file's directory",
        "coordinate_conversion": {
            "source_basis": {"forward": "+Y", "left": "+X", "up": "+Z", "units": "cm"},
            "actor_basis": {"forward": "+X", "right": "+Y", "up": "+Z", "units": "cm"},
            "matrix_actor_from_source": BASIS_MATRIX,
            "equivalent_rotation": "-90 deg about +Z (Hamilton, active)",
            "rotation_quaternion_xyzw": BASIS_QUAT,
            "position_rule": "p_actor = M * p_source",
            "rotation_rule": "q_actor = q_conv * q_source (component-space; bone-local axes unchanged)",
            "yaw_convention": "positive yaw rotates +X toward +Y; anatomical left turn => negative actor yaw",
            "root_motion_handling": "root bone track extracted into data.root_motion (delta from frame 0); "
                                    "pose artefacts are root-relative so the displacement exists exactly once",
        },
        "skeleton": {
            "kind": "reduced_subset_from_samples",
            "is_full_manny_skeleton": False,
            "source": "bones arrays of raw pose files (identical across all sampled clips)",
            "bone_count": len(skeleton_ref) if skeleton_ref else None,
            "bones": [{"name": n, "parent": p} for n, p in skeleton_ref] if skeleton_ref else None,
            "reference_pose": None,
            "bind_pose": None,
            "note": "No bind/reference pose or extra bones are provided; none are invented.",
        },
        "summary": {"total_assets": len(assets), "ready": n_ready,
                    "deferred_missing_samples": sum(1 for a in assets if a["status"] == "deferred_missing_samples")},
        "assets": assets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate animation resources")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    with manifest_path.open("r", encoding="utf-8-sig") as handle:
        manifest = json.load(handle)

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    authored_assets = build_assets(manifest, manifest_path.parent, output_path.parent)
    serialized = json.dumps(authored_assets, ensure_ascii=False, indent=1, allow_nan=False)
    output_path.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
