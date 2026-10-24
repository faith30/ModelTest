import json
from pathlib import Path

root = Path(r"C:/Users/huaqijiang/AppData/Local/Temp/lyra-answer-yrbz70o9")
auth = json.load(open(root / "assets" / "authored_assets.json", encoding="utf-8"))

cycle_assets = []
turn_assets = []
loco_transition_assets = []
idle_assets = []
for a in auth["assets"]:
    aid = a["asset_id"]
    sem = a.get("semantic") or {}
    action = sem.get("action")
    if action == "cycle":
        cycle_assets.append(aid)
    elif action == "turn":
        turn_assets.append(aid)
    elif action == "idle":
        idle_assets.append(aid)
    elif action in ("start", "stop", "pivot"):
        loco_transition_assets.append(aid)

nodes = []
for p in auth["parameters_inputs"] if False else ["velocity_world_cm_s", "acceleration_world_cm_s2", "actor_yaw_degrees", "aim_yaw_degrees", "dt_seconds"]:
    nodes.append({"id": f"input_{p}", "kind": "input", "parameter": p})

nodes.append({
    "id": "locomotion_state",
    "kind": "state_machine",
    "config": {
        "states": ["idle", "start", "cycle", "stop", "pivot", "turn"],
        "description": "flat-ground grounded locomotion state machine; see src/controller.py",
    },
})

def player_node(aid):
    a = next(x for x in auth["assets"] if x["asset_id"] == aid)
    sem = a.get("semantic") or {}
    loop = sem.get("action") == "cycle"
    group = "locomotion"
    if sem.get("action") == "turn":
        group = "turn"
    elif sem.get("action") == "idle":
        group = "idle"
    return {"id": f"player_{aid}", "kind": "player", "asset_id": aid, "loop": loop, "sync_group": group, "status": a.get("status")}

for a in auth["assets"]:
    nodes.append(player_node(a["asset_id"]))

connections = [
    {"from": "input_velocity_world_cm_s", "to": "locomotion_state"},
    {"from": "input_acceleration_world_cm_s2", "to": "locomotion_state"},
    {"from": "input_actor_yaw_degrees", "to": "locomotion_state"},
    {"from": "input_aim_yaw_degrees", "to": "locomotion_state"},
    {"from": "input_dt_seconds", "to": "locomotion_state"},
    {"from": "locomotion_state", "to": "output", "role": "player_selection"},
]

sync_groups = [
    {"group_id": "locomotion", "members": cycle_assets + loco_transition_assets,
     "settings": {"mode": "independent", "note": "timing-only; no authored footstep markers"}},
    {"group_id": "turn", "members": turn_assets,
     "settings": {"mode": "independent", "note": "in-place turns; no footstep markers"}},
    {"group_id": "idle", "members": idle_assets,
     "settings": {"mode": "independent", "note": "idle/hold pose"}},
]

graph = {
    "schema_version": 1,
    "status": "ready",
    "parameters": {
        "inputs": ["velocity_world_cm_s", "acceleration_world_cm_s2", "actor_yaw_degrees", "aim_yaw_degrees", "dt_seconds"],
        "speed_thresholds": {
            "idle_max_cm_s": 20.0,
            "stop_done_cm_s": 8.0,
            "direction_deadzone_cm_s": 20.0,
            "start_end_cm_s": 40.0,
            "cycle_enter_cm_s": 120.0,
            "stop_enter_cm_s": 150.0,
            "turn_max_cm_s": 40.0,
            "turn_exit_cm_s": 60.0,
            "pivot_min_cm_s": 150.0,
            "pivot_angle_degrees": 60.0,
            "aim_yaw_deadzone_degrees": 15.0,
            "gait_blend_low_cm_s": 380.0,
            "gait_blend_high_cm_s": 450.0,
            "accel_resume_cm_s2": 20.0,
            "decel_slope_cm_s2": 80.0,
        },
        "playback": {
            "min_play_rate": 0.05,
            "max_play_rate": 2.0,
            "start_ramp_seconds": 0.5,
            "pivot_seconds": 0.45,
            "velocity_alpha": 0.2,
        },
        "pose_operation_semantics": {
            "extract_root_delta_world": "root delta converted once; apply world delta after pose",
            "aim_yaw_offset": "declarative upper-body yaw offset intent; not an executed pose",
            "hold_sample": "freeze the referenced player at its current sample time",
        },
    },
    "nodes": nodes,
    "connections": connections,
    "sync_groups": sync_groups,
    "output": {
        "blend": "weighted_average",
        "pose_operations_order": ["extract_root_delta_world", "aim_yaw_offset", "hold_sample"],
    },
}

out = root / "config" / "animation_graph.json"
out.write_text(json.dumps(graph, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print("wrote", out, "nodes", len(nodes))
