"""Authoring entry point for the Lyra-style flat-ground locomotion package.

Reads raw/manifest.json and the 15 available 26-bone pose sample files,
converts them from source space to the runtime actor space declared in
INTERFACE.md, and writes:

* assets/processed/<asset_id>.json for every sampled clip that could be
  materialised (plus two derived, time-reversed in-place turn assets).
* a reusable assets/authored_assets.json resource table that also records
  deferred_missing_samples recipes for the 22 metadata-only clips.

Coordinate conversion (explicit, never double-applies root motion):

* positions : [sx, sy, sz] -> [sy, -sx, sz]
* rotations : active Hamilton xyzw; q_runtime = rotZ(-90) * q_source * rotZ(+90)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

_ROTZ_NEG90_XYZW = [0.0, 0.0, -math.sin(math.pi / 4.0), math.cos(math.pi / 4.0)]
_ROTZ_POS90_XYZW = [0.0, 0.0, math.sin(math.pi / 4.0), math.cos(math.pi / 4.0)]


def _qmul(a: list[float], b: list[float]) -> list[float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]


def _qconj(q: list[float]) -> list[float]:
    return [-q[0], -q[1], -q[2], q[3]]


def convert_position(src: list[float]) -> list[float]:
    """Source +X=left, +Y=forward, +Z=up -> runtime +X=forward, +Y=right, +Z=up."""
    sx, sy, sz = src
    return [sy, -sx, sz]


def convert_quaternion(q: list[float]) -> list[float]:
    """Conjugate a source-space active rotation into runtime actor space."""
    return _qmul(_ROTZ_NEG90_XYZW, _qmul(q, _qconj(_ROTZ_NEG90_XYZW)))


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, list):
        return all(_finite(v) for v in value)
    return True


def _load_pose(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data


def _safe_round(values: list[float]) -> list[float]:
    return [float(v) for v in values]


def _metrics_from_root(times: list[float], roots: list[list[float]]) -> dict:
    start = roots[0]
    end = roots[-1]
    duration = max(times[-1] - times[0], 0.0)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = end[2] - start[2]
    horizontal = math.hypot(dx, dy)
    avg_speed = horizontal / duration if duration > 0.0 else 0.0
    return {
        "duration_seconds": duration,
        "root_start_cm": _safe_round(start),
        "root_end_cm": _safe_round(end),
        "root_displacement_cm": [dx, dy, dz],
        "horizontal_displacement_cm": horizontal,
        "average_speed_cm_s": avg_speed,
    }


def _convert_frames(frames: list[dict]) -> list[dict]:
    out: list[dict] = []
    for frame in frames:
        out.append(
            {
                "time": float(frame["time"]),
                "positions": [convert_position(p) for p in frame["positions"]],
                "rotations_xyzw": [convert_quaternion(q) for q in frame["rotations_xyzw"]],
            }
        )
    return out


def _write_product(product_dir: Path, product: dict) -> str:
    product_dir.mkdir(parents=True, exist_ok=True)
    rel_path = f"processed/{product['asset_id']}.json"
    out_path = product_dir.parent / rel_path
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(product, handle, ensure_ascii=False, allow_nan=False)
    return rel_path


def _coordinate_conversion() -> dict:
    return {
        "source_forward": "+Y",
        "source_left": "+X",
        "source_up": "+Z",
        "runtime_actor_forward": "+X",
        "runtime_actor_left": "-Y",
        "runtime_actor_up": "+Z",
        "position_map": "[sx, sy, sz] -> [sy, -sx, sz]",
        "rotation_convention": "active Hamilton xyzw; q_runtime = rotZ(-90) * q_source * rotZ(+90)",
        "rotz_neg90_xyzw": _ROTZ_NEG90_XYZW,
        "root_motion_policy": "root trajectory converted once; runtime must not apply source root displacement again",
    }


def _generic_deferred_recipe(clip: dict) -> dict:
    semantic = clip.get("semantic", {}) or {}
    action = semantic.get("action")
    operations = [
        "convert_source_to_runtime_basis",
        "extract_root_trajectory",
    ]
    if action == "cycle":
        operations += ["derive_loop_range_from_seam", "compute_average_speed"]
    elif action in ("start", "stop", "pivot"):
        operations += ["trim_to_usable_motion_window", "derive_enter_exit_poses"]
    elif action == "turn":
        operations += ["derive_turn_arc_from_root_yaw", "derive_enter_exit_poses"]
    elif action == "idle":
        operations += ["derive_hold_pose", "derive_loop_or_hold_range"]
    return {
        "name": "generic_source_pose_processing",
        "input_pose_file_expected": clip.get("pose_file"),
        "output_space": "component_runtime_actor",
        "output_rotation": "xyzw",
        "operations": operations,
        "resample_hz": clip.get("sample_rate_hz") or 60,
        "note": "Reusable recipe for the metadata-only clip; no curves, timestamps or poses are fabricated until samples exist.",
    }


def build_assets(manifest: dict, manifest_dir: Path) -> dict:
    """Build the authored resource table and write processed product files.

    Products are written to <manifest_dir>/../assets/processed so their
    relative paths resolve from the generated assets/authored_assets.json.
    """
    clips = manifest.get("clips", [])
    if not clips:
        raise ValueError("manifest contains no clips")

    assets_dir = (manifest_dir / ".." / "assets").resolve()
    product_dir = (assets_dir / "processed").resolve()

    skeleton = None
    assets: list[dict] = []
    source_products: dict[str, dict] = {}

    for clip in clips:
        clip_id = clip["clip_id"]
        pose_file = clip.get("pose_file")
        availability = clip.get("availability")

        if availability == "pose_samples" and pose_file:
            pose_path = manifest_dir / pose_file
            if not pose_path.exists():
                raise FileNotFoundError(f"missing pose sample referenced by manifest: {pose_path}")
            source_data = _load_pose(pose_path)

            bones = source_data.get("bones", [])
            if skeleton is None and bones:
                skeleton = {
                    "description": "26-bone component-space subset observed in the available pose samples; full Manny skeleton is not available.",
                    "space": "component",
                    "bones": bones,
                }

            frames = _convert_frames(source_data.get("frames", []))
            times = [f["time"] for f in frames]
            roots = [f["positions"][0] for f in frames]
            metrics = _metrics_from_root(times, roots)

            semantic = clip.get("semantic", {}) or {}
            loop = semantic.get("action") == "cycle"
            product = {
                "schema_version": 1,
                "asset_id": clip_id,
                "source_clip_id": clip_id,
                "space": "component_runtime_actor",
                "rotation": "xyzw",
                "coordinate_conversion": _coordinate_conversion(),
                "bones": bones,
                "frames": frames,
                "metrics": metrics,
                "loop": loop,
                "loop_range_seconds": [0.0, metrics["duration_seconds"]] if loop else None,
            }
            rel_path = _write_product(product_dir, product)
            source_products[clip_id] = product

            assets.append(
                {
                    "asset_id": clip_id,
                    "source_clip_ids": [clip_id],
                    "status": "ready",
                    "kind": "processed_pose",
                    "semantic": semantic,
                    "recipe": {
                        "name": "convert_source_pose_to_runtime",
                        "position_map": _coordinate_conversion()["position_map"],
                        "rotation_conversion": _coordinate_conversion()["rotation_convention"],
                        "root_motion": "converted exactly once; no retarget or resample performed",
                    },
                    "data": {
                        "product_file": rel_path,
                        "metrics": metrics,
                        "loop": loop,
                        "loop_range_seconds": product["loop_range_seconds"],
                    },
                }
            )
        else:
            assets.append(
                {
                    "asset_id": clip_id,
                    "source_clip_ids": [clip_id],
                    "status": "deferred_missing_samples",
                    "kind": "processed_pose",
                    "semantic": clip.get("semantic"),
                    "missing_inputs": [
                        f"raw/{clip.get('pose_file') or 'poses/<unknown>.json'} (pose_file is null in manifest)"
                    ],
                    "recipe": _generic_deferred_recipe(clip),
                    "data": None,
                    "deferred_fallback_hint": "see config/animation_graph.json and IMPLEMENTATION.md for controller fallback behaviour",
                }
            )

    # Derived, materialisable in-place turns by reversing ready turn samples.
    derived_turns = [
        ("turn_right_90_reverse", "motion_33", "reverse of MM_Unarmed_TurnLeft_90"),
        ("turn_left_180_reverse", "motion_36", "reverse of MM_Unarmed_TurnRight_180"),
    ]
    for asset_id, src_clip, description in derived_turns:
        source = source_products.get(src_clip)
        if source is None:
            continue
        rev_frames: list[dict] = []
        for frame in reversed(source["frames"]):
            rev_frames.append(
                {
                    "time": float(frame["time"]),
                    "positions": [list(p) for p in frame["positions"]],
                    "rotations_xyzw": [list(q) for q in frame["rotations_xyzw"]],
                }
            )
        duration = source["metrics"]["duration_seconds"]
        rev_times = [duration - f["time"] for f in rev_frames]
        rev_frames = [dict(f, time=t) for f, t in zip(rev_frames, rev_times)]
        metrics = dict(source["metrics"])
        metrics["root_displacement_cm"] = [0.0, 0.0, 0.0]
        metrics["horizontal_displacement_cm"] = 0.0
        metrics["average_speed_cm_s"] = 0.0

        product = {
            "schema_version": 1,
            "asset_id": asset_id,
            "source_clip_id": src_clip,
            "space": "component_runtime_actor",
            "rotation": "xyzw",
            "coordinate_conversion": _coordinate_conversion(),
            "bones": source["bones"],
            "frames": rev_frames,
            "metrics": metrics,
            "loop": False,
            "loop_range_seconds": None,
        }
        rel_path = _write_product(product_dir, product)
        assets.append(
            {
                "asset_id": asset_id,
                "source_clip_ids": [src_clip],
                "status": "ready",
                "kind": "processed_pose",
                "semantic": {"gait": None, "direction": "right" if "right" in asset_id else "left",
                             "action": "turn", "anatomical_turn_degrees": -90 if "right" in asset_id else 180,
                             "derived": True, "description": description},
                "recipe": {
                    "name": "time_reverse_sampled_turn",
                    "source_asset_id": src_clip,
                    "operation": "reverse frame order; t -> duration - t; component-space poses unchanged",
                    "note": "Derived playback, not an original captured take; does not fabricate new poses.",
                },
                "data": {
                    "product_file": rel_path,
                    "metrics": metrics,
                    "loop": False,
                    "loop_range_seconds": None,
                },
            }
        )

    return {
        "schema_version": 1,
        "status": "ready",
        "source_manifest": "raw/manifest.json",
        "coordinate_conversion": _coordinate_conversion(),
        "skeleton": skeleton,
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

    authored_assets = build_assets(manifest, manifest_path.parent)
    serialized = json.dumps(authored_assets, ensure_ascii=False, indent=2, allow_nan=False)
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
