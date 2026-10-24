"""Self-check: run the controller over synthetic input scenarios (not UE, no pose evaluation)."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from controller import LocomotionController, FrameValidationError  # noqa: E402

graph = json.loads((ROOT / "config/animation_graph.json").read_text(encoding="utf-8"))
assets = json.loads((ROOT / "assets/authored_assets.json").read_text(encoding="utf-8"))
ids = {a["asset_id"]: a["status"] for a in assets["assets"]}
DT = 1 / 60


def sim(segments, actor_yaw_fn=lambda t: 0.0, aim_fn=None, max_accel=1800.0, brake=1400.0):
    """segments: list of (duration, desired_world_velocity_xy). Simple kinematic integrator."""
    frames, v, t = [], [0.0, 0.0], 0.0
    for dur, target in segments:
        n = int(round(dur / DT))
        for _ in range(n):
            dvx, dvy = target[0] - v[0], target[1] - v[1]
            mag = math.hypot(dvx, dvy)
            if math.hypot(*target) < 1e-6:
                acc_in = [0.0, 0.0]
                sp = math.hypot(*v)
                if sp > 0:
                    dec = min(brake * DT, sp)
                    v = [v[0] - v[0] / sp * dec, v[1] - v[1] / sp * dec]
            else:
                acc_in = [dvx / mag * max_accel, dvy / mag * max_accel] if mag > 1e-6 else [target[0] * 0.01, target[1] * 0.01]
                step = min(max_accel * DT, mag)
                if mag > 1e-6:
                    v = [v[0] + dvx / mag * step, v[1] + dvy / mag * step]
            ay = actor_yaw_fn(t)
            frames.append({"dt_seconds": DT, "velocity_world_cm_s": [v[0], v[1], 0.0],
                           "acceleration_world_cm_s2": [acc_in[0], acc_in[1], 0.0],
                           "actor_yaw_degrees": ay, "aim_yaw_degrees": aim_fn(t) if aim_fn else ay})
            t += DT
    return frames


def run(name, frames, verbose=False):
    c = LocomotionController(graph, assets)
    c.reset(0)
    plans = []
    for f in frames:
        plan = c.step(f)
        json.dumps(plan, allow_nan=False)
        for pl in plan["players"]:
            assert pl["asset_id"] in ids, pl
            assert ids[pl["asset_id"]] == "ready", pl
        pids = [pl["player_id"] for pl in plan["players"]]
        assert len(pids) == len(set(pids))
        ws = sum(pl["weight"] for pl in plan["players"])
        assert abs(ws - 1.0) < 1e-4, ws
        oids = [o["operation_id"] for o in plan["pose_operations"]]
        assert len(oids) == len(set(oids))
        plans.append(plan)
    # determinism
    c.reset(0)
    again = [c.step(f) for f in frames]
    assert json.dumps(again) == json.dumps(plans), "non-deterministic"
    states, last = [], None
    for p in plans:
        d = p["diagnostics"]
        for e in d["transitions"]:
            states.append(f"{d['frame_index']}:{e['from']}->{e['to']}({e['condition']})")
        fb = d["fallbacks_this_frame"]
        for x in fb:
            states.append(f"   fallback {x['requested_asset_id']}->{x['used_asset_id']} [{x['policy']}]")
    print(f"== {name}: {len(frames)} frames")
    for s in states:
        print("  ", s)
    if verbose:
        for p in plans[::15]:
            d = p["diagnostics"]
            print("   f%d %s spd=%.0f ryo=%.1f" % (d["frame_index"], d["state"], d["speed_cm_s"], d["root_yaw_offset_deg"]),
                  [(pl["asset_id"], pl["sample_time_seconds"], pl["weight"], pl["play_rate"]) for pl in p["players"]],
                  [o["operation_type"] for o in p["pose_operations"]])
    return plans


V = lambda yaw, s: (s * math.cos(math.radians(yaw)), s * math.sin(math.radians(yaw)))
verbose = "-v" in sys.argv
run("walk fwd start/cycle/stop", sim([(0.5, (0, 0)), (2.5, V(0, 300)), (2.0, (0, 0))]), verbose)
run("jog fwd start->cycle->stop", sim([(0.3, (0, 0)), (2.5, V(0, 600)), (2.0, (0, 0))]), verbose)
run("walk->jog gait change", sim([(2.0, V(0, 300)), (2.0, V(0, 600)), (1.5, (0, 0))]))
run("strafe left walk (start fallback, stop fallback)", sim([(2.0, V(-90, 300)), (2.0, (0, 0))]), verbose)
run("jog fwd pivot to bwd", sim([(2.0, V(0, 600)), (2.0, V(180, 600)), (1.5, (0, 0))], max_accel=2400), verbose)
run("walk fwd pivot (fallback)", sim([(2.0, V(0, 300)), (2.0, V(180, 300))], max_accel=2400))
run("direction change fwd->right->bwd", sim([(1.5, V(0, 600)), (1.5, V(90, 600)), (1.5, V(180, 600)), (1.0, (0, 0))]))
run("turn in place: actor snaps left 90", sim([(0.5, (0, 0)), (3.0, (0, 0))], actor_yaw_fn=lambda t: 0 if t < 0.5 else -90), verbose)
run("turn in place: aim right 90 (fallback)", sim([(3.0, (0, 0))], aim_fn=lambda t: 0 if t < 0.5 else 90))
run("turn in place: actor 180 wrap 350->170", sim([(3.0, (0, 0))], actor_yaw_fn=lambda t: 350 if t < 0.5 else 170 + 720))
run("moving while actor rotates", sim([(3.0, V(0, 600)), (1.0, (0, 0))], actor_yaw_fn=lambda t: 120 * t))

c = LocomotionController(graph, assets)
for bad in [{"dt_seconds": 0, "velocity_world_cm_s": [0, 0, 0], "acceleration_world_cm_s2": [0, 0, 0], "actor_yaw_degrees": 0, "aim_yaw_degrees": 0},
            {"dt_seconds": DT, "velocity_world_cm_s": [float("nan"), 0, 0], "acceleration_world_cm_s2": [0, 0, 0], "actor_yaw_degrees": 0, "aim_yaw_degrees": 0},
            {"dt_seconds": DT, "velocity_world_cm_s": [0, 0, 0], "actor_yaw_degrees": 0, "aim_yaw_degrees": 0}]:
    try:
        c.step(bad)
        raise SystemExit("invalid frame accepted")
    except FrameValidationError as e:
        print("rejected:", e)
print("SELF-CHECK OK (plan-level only; no pose evaluated)")
