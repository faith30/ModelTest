"""Per-frame locomotion planner (see INTERFACE.md, config/animation_graph.json, IMPLEMENTATION.md).

The controller owns the clock: every player's ``sample_time_seconds`` is
authoritative for that frame; ``play_rate`` reports how fast the controller
advanced that time this frame (consumers must not advance it again).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from anim_math import clamp, invert_monotonic_curve, sample_curve, wrap_degrees  # noqa: E402
from locomotion_conditions import CONDITIONS  # noqa: E402

CARDINAL_CENTER = {"fwd": 0.0, "right": 90.0, "bwd": 180.0, "left": -90.0}
MOVING_STATES = ("start", "cycle", "stop", "pivot")
FRAME_FIELDS = ("dt_seconds", "velocity_world_cm_s", "acceleration_world_cm_s2",
                "actor_yaw_degrees", "aim_yaw_degrees")
MAX_DT = 0.25


class FrameValidationError(ValueError):
    """Raised for out-of-domain frames (missing field, non-finite, dt <= 0)."""


class LocomotionController:
    def __init__(self, graph: dict, assets: dict) -> None:
        self.graph = graph
        self.assets = assets
        self.p = dict(graph["parameters"])
        if self.p.get("acceleration_semantics") != "input_intent":
            raise ValueError("only acceleration_semantics='input_intent' is implemented")
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.asset_by_id = {a["asset_id"]: a for a in assets["assets"]}
        sm = next(n for n in graph["nodes"] if n["kind"] == "state_machine")
        self.sm = sm
        self.state_player_node = {s["id"]: s["player_node"] for s in sm["states"]}
        self.transitions = {}
        for t in sorted(sm["transitions"], key=lambda t: t["priority"]):
            self.transitions.setdefault(t["from"], []).append(t)
        self.sync_groups = {g["id"]: g for g in graph["sync_groups"]}
        self.op_order = graph["output"]["pose_operation_order"]
        self._validate_graph()
        self.reset(0)

    # ------------------------------------------------------------------ validation
    def _validate_graph(self) -> None:
        ids = set(self.nodes)
        for c in self.graph["connections"]:
            if c["from"] not in ids or c["to"] not in ids:
                raise ValueError(f"unresolved connection {c}")
        for t in self.sm["transitions"]:
            if t["condition"] not in CONDITIONS:
                raise ValueError(f"unknown condition {t['condition']}")
        for sid, pn in self.state_player_node.items():
            node = self.nodes[pn]
            sel = self.nodes[node["selector"]]
            if node.get("sync_group") and node["sync_group"] not in self.sync_groups:
                raise ValueError(f"unknown sync group {node['sync_group']}")
            for aid in self._table_ids(sel["table"]):
                if aid not in self.asset_by_id:
                    raise ValueError(f"{sel['id']} references unknown asset {aid}")
            for fb in sel.get("fallback", {}).values():
                if "asset_id" in fb and self.asset_by_id.get(fb["asset_id"], {}).get("status") != "ready":
                    raise ValueError(f"fallback {fb['asset_id']} is not a ready asset")
        for op in self.op_order:
            if op not in ids:
                raise ValueError(f"unknown pose op node {op}")

    def _table_ids(self, table):
        if isinstance(table, str):
            yield table
        else:
            for v in table.values():
                yield from self._table_ids(v)

    # ------------------------------------------------------------------ state
    def reset(self, seed: int = 0) -> None:
        self.seed = seed  # no randomness is used; kept for interface determinism
        self.frame_index = 0
        self.state = self.sm["initial_state"]
        self.state_time = 0.0
        self.state_entry_cardinal = "fwd"
        self.players = []
        self.next_player_num = 0
        self.gait = "walk"
        self.cardinal = "fwd"
        self.prev_actor_yaw = None
        self.prev_speed = 0.0
        self.root_yaw_offset = 0.0
        self.braking_est = float(self.p["default_braking_deceleration_cm_s2"])
        self.idle_time = 0.0
        self.start_distance = 0.0
        self.pivot_suppressed = False
        self.pivot_reversed = False
        self.pivot_entry_dir = None
        self.pivot_post_distance = 0.0
        self.turn_scale = 1.0
        self.turn_requested = 0.0
        self.k = {}
        self.unmaterializable = []
        self.events = []

    # ------------------------------------------------------------------ helpers used by predicates
    def asset_data(self, asset_id):
        return self.asset_by_id[asset_id]["data"]

    def asset_ready(self, asset_id):
        return self.asset_by_id.get(asset_id, {}).get("status") == "ready"

    def state_player(self):
        for pl in self.players:
            if pl["state"] == self.state and pl["target"] > 0.0:
                return pl
        return None

    def select_asset(self, selector_id, keys):
        """Return (asset_id_or_None, fallback_policy_or_None, requested_asset_id)."""
        sel = self.nodes[selector_id]
        node = sel["table"]
        if not sel["keys"]:
            node = node["default"]
        for key in sel["keys"]:
            node = node[str(keys[key])]
        requested = node
        if self.asset_ready(requested):
            return requested, None, requested
        fb = sel["fallback"].get(requested) or sel["fallback"].get("*")
        if fb is None:
            raise RuntimeError(f"no ready asset and no fallback for {requested}")
        return fb.get("asset_id"), fb, requested

    # ------------------------------------------------------------------ input
    def _validate_frame(self, frame):
        if not isinstance(frame, dict):
            raise FrameValidationError("frame must be a dict")
        for f in FRAME_FIELDS:
            if f not in frame:
                raise FrameValidationError(f"missing field {f}")
        def num(x, name):
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                raise FrameValidationError(f"{name} must be a finite number")
            return float(x)
        dt = num(frame["dt_seconds"], "dt_seconds")
        if dt <= 0.0:
            raise FrameValidationError("dt_seconds must be > 0")
        vecs = {}
        for f in ("velocity_world_cm_s", "acceleration_world_cm_s2"):
            v = frame[f]
            if not isinstance(v, (list, tuple)) or len(v) != 3:
                raise FrameValidationError(f"{f} must have 3 elements")
            vecs[f] = [num(c, f) for c in v]
        return (dt, vecs["velocity_world_cm_s"], vecs["acceleration_world_cm_s2"],
                num(frame["actor_yaw_degrees"], "actor_yaw_degrees"),
                num(frame["aim_yaw_degrees"], "aim_yaw_degrees"))

    def _cardinal_from_angle(self, ang, current):
        p = self.p
        dz = p["cardinal_deadzone_deg"]
        fwd_lim, bwd_lim = p["cardinal_fwd_half_angle_deg"], p["cardinal_bwd_half_angle_deg"]
        a = abs(ang)
        # hysteresis: widen the currently selected sector by the deadzone
        if current == "fwd" and a <= fwd_lim + dz:
            return "fwd"
        if current == "bwd" and a >= bwd_lim - dz:
            return "bwd"
        if current in ("left", "right") and (fwd_lim - dz) < a < (bwd_lim + dz) and \
                ((ang < 0) == (current == "left")):
            return current
        if a <= fwd_lim:
            return "fwd"
        if a >= bwd_lim:
            return "bwd"
        return "left" if ang < 0 else "right"

    def _derive(self, dt, vel, acc, actor_yaw, aim_yaw):
        p = self.p
        speed = math.hypot(vel[0], vel[1])
        accel_mag = math.hypot(acc[0], acc[1])
        yr = math.radians(actor_yaw)
        def to_local(v):
            return (v[0] * math.cos(yr) + v[1] * math.sin(yr), -v[0] * math.sin(yr) + v[1] * math.cos(yr))
        lv, la = to_local(vel), to_local(acc)
        has_accel = accel_mag > p["accel_input_eps_cm_s2"]
        if speed > p["moving_speed_min_cm_s"]:
            local_angle = math.degrees(math.atan2(lv[1], lv[0]))
        elif has_accel:
            local_angle = math.degrees(math.atan2(la[1], la[0]))
        else:
            local_angle = CARDINAL_CENTER[self.cardinal]
        accel_along = (acc[0] * vel[0] + acc[1] * vel[1]) / speed if speed > 1e-6 else 0.0
        if speed > 1e-6 and accel_mag > 1e-6:
            cosang = clamp((acc[0] * vel[0] + acc[1] * vel[1]) / (speed * accel_mag), -1.0, 1.0)
            av_angle = math.degrees(math.acos(cosang))
        else:
            av_angle = 0.0
        # braking estimate from observed speed drop while no input acceleration
        if not has_accel and self.frame_index > 0 and speed < self.prev_speed:
            obs = (self.prev_speed - speed) / dt
            s = p["braking_estimate_smoothing"]
            self.braking_est = (1 - s) * self.braking_est + s * obs
        # yaw bookkeeping (handles wrap-around)
        dyaw = 0.0 if self.prev_actor_yaw is None else wrap_degrees(actor_yaw - self.prev_actor_yaw)
        self.prev_actor_yaw = actor_yaw
        self.k = {
            "dt": dt, "speed": speed, "accel_mag": accel_mag, "has_accel": has_accel,
            "local_velocity_angle": local_angle, "accel_along_velocity": accel_along,
            "accel_velocity_angle": av_angle, "actor_yaw": actor_yaw, "aim_yaw": aim_yaw,
            "actor_yaw_delta": dyaw, "velocity": vel, "acceleration": acc,
            "accel_local_angle": math.degrees(math.atan2(la[1], la[0])) if has_accel else None,
        }
        # gait with hysteresis
        if self.gait == "walk" and speed > p["gait_walk_to_jog_speed_cm_s"]:
            self.gait = "jog"
        elif self.gait == "jog" and speed < p["gait_jog_to_walk_speed_cm_s"]:
            self.gait = "walk"
        if speed > p["moving_speed_min_cm_s"] or has_accel:
            self.cardinal = self._cardinal_from_angle(local_angle, self.cardinal)

    def _update_root_yaw_offset(self, dt):
        k, p = self.k, self.p
        if self.state in ("idle", "turn_in_place"):
            self.root_yaw_offset -= k["actor_yaw_delta"]  # keep feet planted while capsule rotates
        else:
            tau = max(p["root_yaw_offset_moving_blend_out_s"], 1e-3)
            self.root_yaw_offset *= math.exp(-dt / tau)
        self.root_yaw_offset = wrap_degrees(self.root_yaw_offset)
        lim = p["root_yaw_offset_max_deg"]
        self.root_yaw_offset = clamp(self.root_yaw_offset, -lim, lim)
        mesh_yaw = k["actor_yaw"] + self.root_yaw_offset
        k["turn_error"] = wrap_degrees(k["aim_yaw"] - mesh_yaw)
        k["mesh_yaw"] = wrap_degrees(mesh_yaw)

    # ------------------------------------------------------------------ players
    def _new_player(self, state, asset_id, time, blend_time, time_mode, loop, extra=None, immediate=False):
        pid = f"p{self.next_player_num:04d}_{state}"
        self.next_player_num += 1
        node_id = self.state_player_node[state]
        rate = 1.0 / blend_time if blend_time > 0 else float("inf")
        for pl in self.players:
            pl["target"] = 0.0
            pl["fade_rate"] = rate
        pl = {"player_id": pid, "node_id": node_id, "state": state, "asset_id": asset_id,
              "time": time, "prev_time": time, "play_rate": 1.0, "loop": loop,
              "weight": 1.0 if (immediate or not self.players) else 0.0, "target": 1.0,
              "fade_rate": rate, "time_mode": time_mode}
        if extra:
            pl.update(extra)
        self.players.append(pl)
        return pl

    def _advance_clock(self, pl, dt, rate):
        pl["prev_time"] = pl["time"]
        data = self.asset_data(pl["asset_id"])
        dur = data["duration_seconds"]
        t = pl["time"] + dt * rate
        if pl["loop"] and dur > 0:
            t = math.fmod(t, dur)
        else:
            t = clamp(t, 0.0, dur)
        pl["time"] = t
        pl["play_rate"] = rate

    def _set_matched_time(self, pl, dt, t_match):
        """Distance matching with clamped play rate (time never runs backwards)."""
        p = self.p
        dur = self.asset_data(pl["asset_id"])["duration_seconds"]
        lo = pl["time"] + dt * p["distance_match_min_play_rate"]
        hi = pl["time"] + dt * p["distance_match_max_play_rate"]
        t = clamp(clamp(t_match, lo, hi), 0.0, dur)
        pl["prev_time"] = pl["time"]
        pl["play_rate"] = (t - pl["time"]) / dt
        pl["time"] = t
        pl["distance_match_target_s"] = round(t_match, 5)

    # ------------------------------------------------------------------ sync groups
    def _ref_markers(self, asset_id, ref_name):
        data = self.asset_data(asset_id)
        return sorted(m["time_s"] for m in data.get("sync_markers", []) if m["name"] == ref_name)

    def _stride_at(self, asset_id, t, ref_name):
        """Return (prev_marker, next_marker) bracketing t on the looped marker track, or None."""
        refs = self._ref_markers(asset_id, ref_name)
        if not refs:
            return None
        period = self.asset_data(asset_id)["loop"]["period_s"]
        ext = [r - period for r in refs] + refs + [r + period for r in refs]
        for a, b in zip(ext, ext[1:]):
            if a <= t < b:
                return a, b
        return ext[-2], ext[-1]

    def _phase(self, asset_id, t, settings):
        st = self._stride_at(asset_id, t, settings["phase_reference_marker"])
        if st is None or settings["method"] != "marker_phase":
            return t / self.asset_data(asset_id)["duration_seconds"], "normalized_time"
        a, b = st
        return (t - a) / (b - a), "marker_phase"

    def _time_from_phase(self, asset_id, phase, method, near_t, settings):
        period = self.asset_data(asset_id)["loop"]["period_s"]
        if method == "marker_phase":
            st = self._stride_at(asset_id, near_t, settings["phase_reference_marker"])
            if st is not None:
                a, b = st
                return math.fmod(a + phase * (b - a) + period, period)
        return phase * period

    def _members(self, group_id):
        return [pl for pl in self.players
                if self.nodes[pl["node_id"]].get("sync_group") == group_id]

    def _update_sync_groups(self, dt):
        out = {}
        for gid, g in self.sync_groups.items():
            members = self._members(gid)
            if not members:
                out[gid] = None
                continue
            leader = max(members, key=lambda pl: (pl["weight"] + pl["target"], pl["player_id"]))
            data = self.asset_data(leader["asset_id"])
            rate = clamp(self.k["speed"] / data["authored_speed_cm_s"],
                         self.p["cycle_play_rate_min"], self.p["cycle_play_rate_max"])
            self._advance_clock(leader, dt, rate)
            phase, method = self._phase(leader["asset_id"], leader["time"], g["settings"])
            for pl in members:
                if pl is leader:
                    continue
                pl["prev_time"] = pl["time"]
                nt = self._time_from_phase(pl["asset_id"], phase, method, pl["time"], g["settings"])
                per = self.asset_data(pl["asset_id"])["loop"]["period_s"]
                adv = math.fmod(nt - pl["time"] + per, per)
                pl["time"] = nt
                pl["play_rate"] = adv / dt if adv < 0.5 * per else 0.0
            out[gid] = {"leader": leader["player_id"], "phase": phase, "method": method}
        return out

    # ------------------------------------------------------------------ state entry
    def _note_fallback(self, state, requested, fb):
        self.unmaterializable.append({
            "state": state, "requested_asset_id": requested,
            "requested_status": self.asset_by_id[requested]["status"],
            "policy": fb["policy"], "used_asset_id": fb.get("asset_id"),
            "reason": fb["reason"]})

    def _enter_state(self, state, blend_time, reason):
        k, p = self.k, self.p
        prev = self.state
        self.events.append({"from": prev, "to": state, "condition": reason})
        self.state, self.state_time = state, 0.0
        self.state_entry_cardinal = self.cardinal
        keys = {"gait": self.gait, "cardinal": self.cardinal}
        if state == "idle":
            aid, fb, req = self.select_asset("sel_idle", {})
            if fb:
                self._note_fallback(state, req, fb)
            self._new_player("idle", aid, 0.0, blend_time, "static_pose" if fb else "clock_loop",
                             loop=not fb, extra={"substitutes_for_asset_id": req if fb else None,
                                                 "frame_index": self.asset_data(aid).get("frame_index")})
        elif state == "start":
            aid, fb, req = self.select_asset("sel_start", keys)
            if fb:
                self._note_fallback(state, req, fb)
                return self._enter_state(fb["target_state"], blend_time, "fallback_skip:" + req)
            self.start_distance = 0.0
            self._new_player("start", aid, 0.0, blend_time, "distance_match", loop=False)
        elif state == "cycle":
            self._enter_cycle(blend_time)
        elif state == "stop":
            aid, fb, req = self.select_asset("sel_stop", keys)
            if fb:
                self._note_fallback(state, req, fb)
                stop_t = clamp(k["speed"] / max(self.braking_est, 1.0), 0.2, 1.5)
                self._new_player("stop", aid, 0.0, stop_t, "timed_blend", loop=False,
                                 extra={"substitutes_for_asset_id": req,
                                        "frame_index": self.asset_data(aid)["frame_index"]})
            else:
                d = k["speed"] ** 2 / (2.0 * max(self.braking_est, 1.0))
                c = self.asset_data(aid)["curves"]
                t0 = invert_monotonic_curve(c["time_s"], c["distance_to_stop_cm"], d)
                self._new_player("stop", aid, t0, blend_time, "distance_match", loop=False)
        elif state == "pivot":
            aid, fb, req = self.select_asset("sel_pivot", keys)
            if fb:
                self._note_fallback(state, req, fb)
                self.pivot_suppressed = True
                self.state = prev  # stay in cycle; the cycle selection follows the velocity reversal
                self.events[-1]["to"] = prev
                if prev != "cycle":
                    return self._enter_state("cycle", blend_time, "fallback_skip:" + req)
                return None
            data = self.asset_data(aid)
            expected_exit = CARDINAL_CENTER[self.cardinal] + wrap_degrees(
                data["exit_velocity_heading_actor_deg"] - data["entry_velocity_heading_actor_deg"])
            mismatch = abs(wrap_degrees(k["accel_local_angle"] - expected_exit))
            if mismatch > p["pivot_exit_direction_tolerance_deg"]:
                self.unmaterializable.append({"state": state, "requested_asset_id": aid, "requested_status": "ready",
                                              "policy": "skip_state", "used_asset_id": None,
                                              "reason": f"pivot exit direction mismatch {mismatch:.1f} deg"})
                self.pivot_suppressed = True
                self.state = prev
                self.events[-1]["to"] = prev
                if prev != "cycle":
                    return self._enter_state("cycle", blend_time, "pivot_direction_mismatch")
                return None
            v = k["velocity"]
            self.pivot_entry_dir = (v[0] / k["speed"], v[1] / k["speed"])
            self.pivot_reversed = False
            self.pivot_post_distance = 0.0
            d = k["speed"] ** 2 / (2.0 * max(-k["accel_along_velocity"], 1.0))
            c = self.asset_data(aid)["curves"]
            t0 = invert_monotonic_curve(c["time_s"], c["signed_distance_to_pivot_cm"], -d)
            self._new_player("pivot", aid, t0, blend_time, "distance_match_to_marker", loop=False)
        elif state == "turn_in_place":
            req_yaw = k["turn_error"]
            side = "right" if req_yaw > 0 else "left"
            size = "180" if abs(req_yaw) > p["turn_select_180_above_deg"] else "90"
            aid, fb, req = self.select_asset("sel_turn", {"turn_side": side, "turn_size": size})
            if fb:
                self._note_fallback(state, req, fb)
            total = self.asset_data(aid)["total_root_yaw_actor_deg"]
            if total * req_yaw < 0:
                req_yaw += 360.0 * math.copysign(1.0, total)
            self.turn_requested = req_yaw
            self.turn_scale = req_yaw / total
            self._new_player("turn_in_place", aid, 0.0, blend_time, "clock_once", loop=False,
                             extra={"substitutes_for_asset_id": req if fb else None,
                                    "root_yaw_scale": self.turn_scale,
                                    "requested_turn_yaw_deg": req_yaw})
        return None

    def _enter_cycle(self, blend_time):
        aid, _fb, _req = self.select_asset("sel_cycle", {"gait": self.gait, "cardinal": self.cardinal})
        settings = self.sync_groups["locomotion_cycle"]["settings"]
        existing = [pl for pl in self._members("locomotion_cycle") if pl["weight"] > 0]
        if existing:
            lead = max(existing, key=lambda pl: pl["weight"])
            ph, m = self._phase(lead["asset_id"], lead["time"], settings)
            t0 = self._time_from_phase(aid, ph, m, 0.0, settings)
        else:
            src = next((pl for pl in reversed(self.players) if pl["state"] in ("start", "pivot")), None)
            t0 = self._cycle_time_from_contacts(src, aid) if src else 0.0
        self._new_player("cycle", aid, t0, blend_time, "speed_scaled_clock", loop=True)

    def _cycle_time_from_contacts(self, src, cycle_id):
        """Align the cycle to the foot that most recently planted in the outgoing clip."""
        contacts = self.asset_data(src["asset_id"]).get("foot_contacts", {})
        best = None
        for side, ivs in contacts.items():
            for s, _e in ivs:
                if s <= src["time"] and (best is None or s > best[1]):
                    best = (side, s)
        if best is None:
            return 0.0
        side, s = best
        marks = [m["time_s"] for m in self.asset_data(cycle_id)["sync_markers"] if m["name"] == f"foot_{side}_plant"]
        if not marks:
            return 0.0
        per = self.asset_data(cycle_id)["loop"]["period_s"]
        return math.fmod(marks[0] + (src["time"] - s), per)

    # ------------------------------------------------------------------ main
    def step(self, frame: dict) -> dict:
        dt_raw, vel, acc, actor_yaw, aim_yaw = self._validate_frame(frame)
        dt = min(dt_raw, MAX_DT)
        self.events = []
        self.unmaterializable = []
        self._derive(dt, vel, acc, actor_yaw, aim_yaw)
        self._update_root_yaw_offset(dt)
        k, p = self.k, self.p

        if not self.players:
            self._enter_state(self.state, 0.0, "initial")
        if self.pivot_suppressed and (k["accel_velocity_angle"] < p["pivot_min_angle_deg"]
                                      or k["speed"] < p["pivot_min_speed_cm_s"] or not k["has_accel"]):
            self.pivot_suppressed = False
        for t in self.transitions.get(self.state, []):
            if CONDITIONS[t["condition"]](self):
                self._enter_state(t["to"], t["blend_time_s"], t["condition"])
                break
        if self.state == "cycle":
            sp = self.state_player()
            want = self.select_asset("sel_cycle", {"gait": self.gait, "cardinal": self.cardinal})[0]
            if sp is None or sp["asset_id"] != want:
                self.events.append({"from": "cycle", "to": "cycle", "condition": "gait_or_cardinal_changed"})
                self._enter_cycle(0.2)

        self._advance_players(dt)
        sync_info = self._update_sync_groups(dt)
        self._update_weights(dt)
        self.state_time += dt
        self.idle_time = self.idle_time + dt if self.state == "idle" else 0.0
        self.prev_speed = k["speed"]
        plan = self._build_plan(sync_info, dt_raw, dt)
        self.frame_index += 1
        return plan

    def _advance_players(self, dt):
        k, p = self.k, self.p
        for pl in self.players:
            node = self.nodes[pl["node_id"]]
            if node.get("sync_group"):
                continue  # advanced by the sync group
            mode = pl["time_mode"]
            active = pl["state"] == self.state and pl["target"] > 0
            c = self.asset_data(pl["asset_id"]).get("curves", {})
            if mode in ("static_pose", "timed_blend"):
                pl["prev_time"], pl["play_rate"] = pl["time"], 0.0
            elif not active:
                self._advance_clock(pl, dt, 1.0)
            elif mode == "distance_match" and pl["state"] == "start":
                self.start_distance += k["speed"] * dt
                tm = invert_monotonic_curve(c["time_s"], c["distance_traveled_cm"], self.start_distance)
                self._set_matched_time(pl, dt, tm)
            elif mode == "distance_match" and pl["state"] == "stop":
                if k["speed"] <= p["idle_speed_max_cm_s"]:
                    self._advance_clock(pl, dt, 1.0)
                else:
                    d = k["speed"] ** 2 / (2.0 * max(self.braking_est, 1.0))
                    self._set_matched_time(pl, dt, invert_monotonic_curve(c["time_s"], c["distance_to_stop_cm"], d))
            elif mode == "distance_match_to_marker":
                v = k["velocity"]
                if not self.pivot_reversed and (v[0] * self.pivot_entry_dir[0] + v[1] * self.pivot_entry_dir[1]) <= 0.1 * k["speed"]:
                    self.pivot_reversed = True
                if self.pivot_reversed:
                    self.pivot_post_distance += k["speed"] * dt
                    target = self.pivot_post_distance
                else:
                    target = -k["speed"] ** 2 / (2.0 * max(-k["accel_along_velocity"], 1.0))
                self._set_matched_time(pl, dt, invert_monotonic_curve(c["time_s"], c["signed_distance_to_pivot_cm"], target))
            elif mode == "clock_once":
                self._advance_clock(pl, dt, 1.0)
                if pl["state"] == "turn_in_place":
                    y0 = sample_curve(c["time_s"], c["root_yaw_deg"], pl["prev_time"])
                    y1 = sample_curve(c["time_s"], c["root_yaw_deg"], pl["time"])
                    self.root_yaw_offset += (y1 - y0) * pl.get("root_yaw_scale", 1.0)
            else:
                self._advance_clock(pl, dt, 1.0)

    def _update_weights(self, dt):
        for pl in self.players:
            step = dt * pl["fade_rate"]
            if pl["weight"] < pl["target"]:
                pl["weight"] = min(pl["target"], pl["weight"] + step)
            else:
                pl["weight"] = max(pl["target"], pl["weight"] - step)
        eps = self.p["blend_epsilon"]
        self.players = [pl for pl in self.players if pl["weight"] > eps or pl["target"] > 0]

    # ------------------------------------------------------------------ output
    def _build_plan(self, sync_info, dt_raw, dt):
        k, p = self.k, self.p
        total = sum(pl["weight"] for pl in self.players) or 1.0
        players = []
        for pl in self.players:
            a = self.asset_by_id[pl["asset_id"]]
            entry = {
                "player_id": pl["player_id"], "asset_id": pl["asset_id"],
                "sample_time_seconds": round(pl["time"], 6),
                "weight": round(pl["weight"] / total, 6),
                "play_rate": round(pl["play_rate"], 6), "loop": pl["loop"],
                "node_id": pl["node_id"], "state": pl["state"], "time_mode": pl["time_mode"],
                "target_weight": pl["target"], "asset_status": a["status"],
                "materializable": a["status"] == "ready",
                "root_motion": "ignored_capsule_driven",
            }
            if pl.get("substitutes_for_asset_id"):
                entry["substitutes_for_asset_id"] = pl["substitutes_for_asset_id"]
                entry["substituted_asset_status"] = self.asset_by_id[pl["substitutes_for_asset_id"]]["status"]
            if pl.get("frame_index") is not None:
                entry["frame_index"] = pl["frame_index"]
            if "root_yaw_scale" in pl:
                entry["root_yaw_scale"] = round(pl["root_yaw_scale"], 6)
                entry["requested_turn_yaw_deg"] = round(pl["requested_turn_yaw_deg"], 6)
            if "distance_match_target_s" in pl:
                entry["distance_match_target_s"] = pl["distance_match_target_s"]
            players.append(entry)

        groups = []
        for gid, g in self.sync_groups.items():
            info = sync_info.get(gid)
            settings = dict(g["settings"])
            settings["leader_player_id"] = info["leader"] if info else None
            settings["leader_phase"] = round(info["phase"], 6) if info else None
            settings["method_used"] = info["method"] if info else None
            groups.append({"group_id": gid,
                           "member_player_ids": [pl["player_id"] for pl in self._members(gid)],
                           "settings": settings})

        ops = [{"operation_id": "state_blend", "operation_type": "weighted_blend",
                "inputs": [e["player_id"] for e in players],
                "parameters": {"weights": {e["player_id"]: e["weight"] for e in players}, "normalized": True}}]
        last = "state_blend"
        moving = self.state in MOVING_STATES
        warp = 0.0
        if moving:
            warp = clamp(wrap_degrees(k["local_velocity_angle"] - CARDINAL_CENTER[self.cardinal]),
                         -p["orientation_warp_max_deg"], p["orientation_warp_max_deg"])
        stride = None
        sp = self.state_player()
        if self.state == "cycle" and sp is not None and k["speed"] > p["moving_speed_min_cm_s"]:
            d = self.asset_data(sp["asset_id"])
            denom = d["authored_speed_cm_s"] * max(sp["play_rate"], 1e-6)
            stride = clamp(k["speed"] / denom, 0.5, 1.5)
        aim = clamp(wrap_degrees(k["aim_yaw"] - k["mesh_yaw"]), -p["aim_yaw_limit_deg"], p["aim_yaw_limit_deg"])
        for op_id in self.op_order:
            node = self.nodes[op_id]
            typ = node["operation_type"]
            if typ == "rotate_root_yaw":
                if abs(self.root_yaw_offset) < 0.01:
                    continue
                params = {"yaw_deg": round(self.root_yaw_offset, 6),
                          "mesh_world_yaw_deg": round(k["mesh_yaw"], 6),
                          "actor_world_yaw_deg": k["actor_yaw"],
                          "convention": "positive rotates +X toward +Y about +Z"}
            elif typ == "orientation_warping":
                if abs(warp) < 0.01:
                    continue
                params = {"angle_deg": round(warp, 6), "bones": p["orientation_warp_bones"],
                          "cardinal": self.cardinal,
                          "velocity_local_angle_deg": round(k["local_velocity_angle"], 6)}
            elif typ == "stride_warping":
                if stride is None or abs(stride - 1.0) < 0.01:
                    continue
                params = {"stride_scale": round(stride, 6), "axis": "local velocity direction", "ik_executed": False}
            elif typ == "spine_yaw_distribution":
                if abs(aim) < 0.5:
                    continue
                params = {"aim_offset_deg": round(aim, 6),
                          "per_bone_yaw_deg": {b: round(aim * w, 6)
                                               for b, w in zip(p["aim_spine_bones"], p["aim_spine_weights"])}}
            else:
                continue
            ops.append({"operation_id": op_id, "operation_type": typ, "inputs": [last], "parameters": params})
            last = op_id

        deferred_active = [
            {"player_id": pl["player_id"], "requested_asset_id": pl["substitutes_for_asset_id"],
             "status": self.asset_by_id[pl["substitutes_for_asset_id"]]["status"], "materialized": False}
            for pl in self.players if pl.get("substitutes_for_asset_id")]
        return {
            "schema_version": 1,
            "players": players,
            "sync_groups": groups,
            "pose_operations": ops,
            "diagnostics": {
                "frame_index": self.frame_index, "state": self.state,
                "state_time_s": round(self.state_time, 6), "transitions": self.events,
                "gait": self.gait, "cardinal": self.cardinal,
                "speed_cm_s": round(k["speed"], 4),
                "local_velocity_angle_deg": round(k["local_velocity_angle"], 4),
                "accel_velocity_angle_deg": round(k["accel_velocity_angle"], 4),
                "braking_deceleration_estimate_cm_s2": round(self.braking_est, 4),
                "root_yaw_offset_deg": round(self.root_yaw_offset, 4),
                "turn_error_deg": round(k["turn_error"], 4),
                "fallbacks_this_frame": self.unmaterializable,
                "deferred_assets_substituted": deferred_active,
                "dt_clamped": dt_raw != dt, "dt_used_s": dt,
                "note": "execution plan only; no pose was evaluated",
            },
        }
