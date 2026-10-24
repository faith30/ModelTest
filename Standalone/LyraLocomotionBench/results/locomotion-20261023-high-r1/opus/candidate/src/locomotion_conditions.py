"""Named transition predicates referenced by config/animation_graph.json.

Each predicate receives the controller (read-only use) and returns bool. The
controller validates at construction that every ``condition`` string in the
graph exists in ``CONDITIONS``.

Acceleration semantics ("input_intent", Lyra/CharacterMovement style): the
acceleration input is the movement intent. Zero acceleration while moving
means the character is braking to a stop; acceleration opposing velocity
means a direction reversal (pivot).
"""

from __future__ import annotations


def wants_to_move(c) -> bool:
    return c.k["has_accel"]


def wants_to_stop(c) -> bool:
    return not c.k["has_accel"]


def pivot_requested(c) -> bool:
    k, p = c.k, c.p
    if c.pivot_suppressed:
        return False
    return (k["has_accel"] and k["speed"] >= p["pivot_min_speed_cm_s"]
            and k["accel_mag"] >= p["pivot_min_accel_cm_s2"]
            and k["accel_velocity_angle"] >= p["pivot_min_angle_deg"])


def start_finished(c) -> bool:
    pl = c.state_player()
    if pl is None:
        return True
    data = c.asset_data(pl["asset_id"])
    dur = data["duration_seconds"]
    if pl["time"] >= c.p["start_exit_max_time_ratio"] * dur:
        return True
    cyc = c.select_asset("sel_cycle", {"gait": c.gait, "cardinal": c.cardinal})[0]
    target = c.asset_data(cyc)["authored_speed_cm_s"] if c.asset_ready(cyc) else None
    if target and c.k["speed"] >= c.p["start_exit_speed_ratio"] * target:
        return True
    if c.cardinal != c.state_entry_cardinal:
        return True
    return False


def pivot_finished(c) -> bool:
    pl = c.state_player()
    if pl is None:
        return True
    data = c.asset_data(pl["asset_id"])
    if pl["time"] >= data["pivot_time_s"] + c.p["pivot_exit_after_pivot_s"] and c.pivot_reversed:
        return True
    return pl["time"] >= data["duration_seconds"]


def stop_finished(c) -> bool:
    pl = c.state_player()
    slow = c.k["speed"] <= c.p["idle_speed_max_cm_s"]
    if pl is None:
        return slow
    if pl.get("time_mode") == "timed_blend":
        return slow and pl["weight"] >= 1.0 - c.p["blend_epsilon"]
    data = c.asset_data(pl["asset_id"])
    return slow and pl["time"] >= data.get("root_at_rest_time_s", data["duration_seconds"])


def turn_needed(c) -> bool:
    return (c.idle_time >= c.p["turn_min_idle_time_s"]
            and abs(c.k["turn_error"]) > c.p["turn_trigger_deg"])


def turn_finished(c) -> bool:
    pl = c.state_player()
    if pl is None:
        return True
    data = c.asset_data(pl["asset_id"])
    return pl["time"] >= min(data["duration_seconds"], data["turn_end_time_s"] + 0.3)


CONDITIONS = {
    "wants_to_move": wants_to_move,
    "wants_to_stop": wants_to_stop,
    "pivot_requested": pivot_requested,
    "start_finished": start_finished,
    "pivot_finished": pivot_finished,
    "stop_finished": stop_finished,
    "turn_needed": turn_needed,
    "turn_finished": turn_finished,
}
