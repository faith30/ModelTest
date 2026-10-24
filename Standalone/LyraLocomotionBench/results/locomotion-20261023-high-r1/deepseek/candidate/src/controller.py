"""Per-frame locomotion controller.

Consumes config/animation_graph.json and assets/authored_assets.json.
Returns a JSON-serialisable execution plan (players, sync groups, pose
operations) for one input frame.  It never returns rendered poses; pose
operations are execution intents (see graph parameters.pose_operation_semantics).

State machine (flat ground, continuously grounded, unarmed):

  idle -> turn        in-place turn when stopped and aim yaw diverges from actor yaw
  idle -> start       locomotion requested from rest
  start -> cycle      start clip finished or speed crosses cycle_enter_cm_s
  cycle -> stop       decelerating below stop_enter_cm_s
  stop -> idle        speed below stop_done_cm_s; last pose is held
  cycle -> pivot      large aim/actor yaw delta while moving; short pivot, then cycle
  turn -> idle/start  turn arc complete or locomotion overrides the turn

Ready sampled assets are played directly.  deferred_missing_samples assets are
still referenced in the plan with materialized=false and a documented
materialisable fallback (direction-matched cycle ramp, or a derived
time-reversed turn), so no fabricated pose is ever claimed.
"""

from __future__ import annotations

import math
from typing import Any

_SCHEMA_VERSION = 1
_REQUIRED_FIELDS = (
    "dt_seconds",
    "velocity_world_cm_s",
    "acceleration_world_cm_s2",
    "actor_yaw_degrees",
    "aim_yaw_degrees",
)


def _wrap180(deg: float) -> float:
    deg = math.fmod(deg + 180.0, 360.0)
    if deg <= 0.0:
        deg += 360.0
    return deg - 180.0


def _finite(x: Any) -> bool:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return math.isfinite(float(x))
    if isinstance(x, (list, tuple)):
        return all(_finite(v) for v in x)
    return True


class LocomotionController:
    def __init__(self, graph: dict, assets: dict) -> None:
        if not isinstance(graph, dict) or not isinstance(assets, dict):
            raise ValueError("graph and assets must be dicts parsed from JSON")

        self.graph = graph
        self.assets = assets

        asset_list = assets.get("assets")
        if not isinstance(asset_list, list):
            raise ValueError("authored_assets.json must contain an assets list")
        self.asset_map: dict[str, dict] = {}
        for asset in asset_list:
            asset_id = asset.get("asset_id")
            if not asset_id:
                raise ValueError("asset entry missing asset_id")
            self.asset_map[asset_id] = asset

        params = graph.get("parameters") or {}
        self.params = params
        self.thresholds = params.get("speed_thresholds") or {}
        self.playback = params.get("playback") or {}
        self.pose_semantics = params.get("pose_operation_semantics") or {}

        self.player_specs: dict[str, dict] = {}
        for node in graph.get("nodes") or []:
            if node.get("kind") == "player":
                self.player_specs[node.get("asset_id")] = node
        self.sync_group_defs = graph.get("sync_groups") or []
        self.output_config = graph.get("output") or {}

        self.reset(seed=0)

    def _asset_status(self, asset_id: str) -> str:
        asset = self.asset_map.get(asset_id)
        return asset.get("status") if asset else "unknown"

    def _is_ready(self, asset_id: str) -> bool:
        return self._asset_status(asset_id) == "ready"

    def _duration(self, asset_id: str) -> float:
        asset = self.asset_map.get(asset_id) or {}
        data = asset.get("data") or {}
        metrics = data.get("metrics") or {}
        dur = metrics.get("duration_seconds")
        if isinstance(dur, (int, float)) and math.isfinite(float(dur)):
            return float(dur)
        return 0.0

    def _avg_speed(self, asset_id: str) -> float:
        asset = self.asset_map.get(asset_id) or {}
        data = asset.get("data") or {}
        metrics = data.get("metrics") or {}
        speed = metrics.get("average_speed_cm_s")
        if isinstance(speed, (int, float)) and math.isfinite(float(speed)):
            return float(speed)
        return 0.0

    def _loop_spec(self, asset_id: str) -> bool:
        spec = self.player_specs.get(asset_id) or {}
        if "loop" in spec:
            return bool(spec["loop"])
        asset = self.asset_map.get(asset_id) or {}
        data = asset.get("data") or {}
        return bool(data.get("loop"))

    def reset(self, seed: int = 0) -> None:
        self.seed = int(seed)
        self.clock = 0.0
        self.mode = "idle"
        self.mode_elapsed = 0.0
        self.sample_times: dict[str, float] = {}
        self.last_velocity = [0.0, 0.0, 0.0]
        self.smoothed_velocity = [0.0, 0.0, 0.0]
        self.smoothed_aim_yaw = None
        self.direction = "fwd"
        self.gait = "walk"
        self.hold_asset_id: str | None = None
        self.hold_sample_time = 0.0
        self.turn_state: dict | None = None
        self.pivot_elapsed = 0.0
        self.pivot_asset_id: str | None = None
        self.deferred_deps: list[str] = []

    def _validate_frame(self, frame: dict):
        if not isinstance(frame, dict):
            raise ValueError("frame must be a dict")
        for key in _REQUIRED_FIELDS:
            if key not in frame:
                raise ValueError(f"frame missing required field: {key}")

        dt = frame["dt_seconds"]
        if not isinstance(dt, (int, float)) or isinstance(dt, bool):
            raise ValueError("dt_seconds must be a finite positive number")
        dt = float(dt)
        if not math.isfinite(dt) or dt <= 0.0:
            raise ValueError(f"dt_seconds must be finite and positive, got {dt!r}")

        velocity = frame["velocity_world_cm_s"]
        acceleration = frame["acceleration_world_cm_s2"]
        actor_yaw = frame["actor_yaw_degrees"]
        aim_yaw = frame["aim_yaw_degrees"]

        for name, value in (
            ("velocity_world_cm_s", velocity),
            ("acceleration_world_cm_s2", acceleration),
        ):
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError(f"{name} must be a 3-element array")
            if not _finite(value):
                raise ValueError(f"{name} must contain only finite numbers")

        for name, value in (("actor_yaw_degrees", actor_yaw), ("aim_yaw_degrees", aim_yaw)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} must be a finite number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")

        return (
            dt,
            [float(v) for v in velocity],
            [float(v) for v in acceleration],
            float(actor_yaw),
            float(aim_yaw),
        )

    @staticmethod
    def _rotate_to_local(v: list[float], yaw_deg: float):
        yaw = math.radians(yaw_deg)
        c, s = math.cos(yaw), math.sin(yaw)
        x, y = v[0], v[1]
        return (c * x + s * y, -s * x + c * y)

    def _direction_from_local(self, lx: float, ly: float, speed: float) -> str:
        dead = float(self.thresholds.get("direction_deadzone_cm_s", 20.0))
        if speed < dead:
            return self.direction
        if abs(lx) >= abs(ly):
            return "fwd" if lx >= 0.0 else "bwd"
        return "left" if ly < 0.0 else "right"

    def _gait_mix(self, speed: float) -> float:
        low = float(self.thresholds.get("gait_blend_low_cm_s", 380.0))
        high = float(self.thresholds.get("gait_blend_high_cm_s", 450.0))
        if high <= low:
            return 0.0 if speed < high else 1.0
        if speed <= low:
            return 0.0
        if speed >= high:
            return 1.0
        return (speed - low) / (high - low)

    def _dominant_gait(self, mix: float) -> str:
        return "jog" if mix >= 0.5 else "walk"

    def _cycle_asset(self, gait: str, direction: str) -> str:
        return self._sel_asset("cycle", gait, direction)

    def _start_asset(self, gait: str, direction: str) -> str:
        return self._sel_asset("start", gait, direction)

    def _stop_asset(self, gait: str, direction: str) -> str:
        return self._sel_asset("stop", gait, direction)

    def _pivot_asset(self, gait: str, direction: str) -> str:
        return self._sel_asset("pivot", gait, direction)

    def _sel_asset(self, action: str, gait: str, direction: str) -> str:
        table = {
            ("cycle", "walk", "fwd"): "motion_01",
            ("cycle", "walk", "bwd"): "motion_05",
            ("cycle", "walk", "left"): "motion_09",
            ("cycle", "walk", "right"): "motion_13",
            ("cycle", "jog", "fwd"): "motion_17",
            ("cycle", "jog", "bwd"): "motion_21",
            ("cycle", "jog", "left"): "motion_25",
            ("cycle", "jog", "right"): "motion_29",
            ("start", "walk", "fwd"): "motion_02",
            ("start", "walk", "bwd"): "motion_06",
            ("start", "walk", "left"): "motion_10",
            ("start", "walk", "right"): "motion_14",
            ("start", "jog", "fwd"): "motion_18",
            ("start", "jog", "bwd"): "motion_22",
            ("start", "jog", "left"): "motion_26",
            ("start", "jog", "right"): "motion_30",
            ("stop", "walk", "fwd"): "motion_03",
            ("stop", "walk", "bwd"): "motion_07",
            ("stop", "walk", "left"): "motion_11",
            ("stop", "walk", "right"): "motion_15",
            ("stop", "jog", "fwd"): "motion_19",
            ("stop", "jog", "bwd"): "motion_23",
            ("stop", "jog", "left"): "motion_27",
            ("stop", "jog", "right"): "motion_31",
            ("pivot", "walk", "fwd"): "motion_04",
            ("pivot", "walk", "bwd"): "motion_08",
            ("pivot", "walk", "left"): "motion_12",
            ("pivot", "walk", "right"): "motion_16",
            ("pivot", "jog", "fwd"): "motion_20",
            ("pivot", "jog", "bwd"): "motion_24",
            ("pivot", "jog", "left"): "motion_28",
            ("pivot", "jog", "right"): "motion_32",
        }
        asset_id = table.get((action, gait, direction))
        if asset_id is None or asset_id not in self.asset_map:
            raise ValueError(f"no asset mapped for {action}/{gait}/{direction}")
        return asset_id

    def _turn_asset(self, delta_deg: float) -> str:
        if delta_deg >= 0.0:
            if abs(delta_deg) <= 135.0:
                return "motion_33"
            return "turn_left_180_reverse"
        if abs(delta_deg) <= 135.0:
            return "turn_right_90_reverse"
        return "motion_36"

    def _turn_arc_degrees(self, asset_id: str) -> float:
        if asset_id == "motion_33":
            return 90.0
        if asset_id == "motion_36":
            return -180.0
        if asset_id == "turn_left_180_reverse":
            return 180.0
        if asset_id == "turn_right_90_reverse":
            return -90.0
        return 0.0

    def _advance(self, asset_id: str, dt: float, play_rate: float, loop: bool) -> float:
        current = self.sample_times.get(asset_id, 0.0)
        current += dt * play_rate
        dur = self._duration(asset_id)
        if loop and dur > 0.0:
            current = math.fmod(current, dur)
            if current < 0.0:
                current += dur
        elif dur > 0.0 and current > dur:
            current = dur
        self.sample_times[asset_id] = current
        return current

    def _player(self, asset_id: str, weight: float, play_rate: float, loop=None) -> dict:
        loop = self._loop_spec(asset_id) if loop is None else loop
        sample_time = self.sample_times.get(asset_id, 0.0)
        materialized = self._is_ready(asset_id)
        entry = {
            "player_id": f"player_{asset_id}",
            "asset_id": asset_id,
            "sample_time_seconds": float(sample_time),
            "weight": float(weight),
            "play_rate": float(play_rate),
            "loop": bool(loop),
            "materialized": materialized,
        }
        if not materialized:
            entry["status"] = "deferred_missing_samples"
        return entry

    def _sync_groups_for(self, members):
        groups = []
        if members:
            groups.append(
                {
                    "group_id": "locomotion",
                    "member_player_ids": list(members),
                    "settings": {
                        "mode": "independent",
                        "note": "no authored footstep/notify markers; sync is timing-only",
                    },
                }
            )
        return groups

    def _pose_operations(self, player_ids, aim_offset, hold=False):
        ops = []
        if player_ids:
            ops.append(
                {
                    "operation_id": "root_motion",
                    "operation_type": "extract_root_delta_world",
                    "inputs": {"player_ids": list(player_ids)},
                    "parameters": {
                        "axis_mapping": "actor_yaw_degrees",
                        "scale": 1.0,
                        "semantics": self.pose_semantics.get(
                            "extract_root_delta_world",
                            "root delta converted once; apply world delta after pose",
                        ),
                    },
                }
            )
            ops.append(
                {
                    "operation_id": "aim_offset",
                    "operation_type": "aim_yaw_offset",
                    "inputs": {"player_ids": list(player_ids)},
                    "parameters": {
                        "yaw_offset_degrees": float(aim_offset),
                        "space": "actor_local",
                        "target_bones": [
                            "spine_01", "spine_02", "spine_03", "spine_04", "spine_05",
                            "neck_01", "neck_02", "head",
                        ],
                        "semantics": self.pose_semantics.get(
                            "aim_yaw_offset",
                            "declarative upper-body yaw offset intent; not an executed pose",
                        ),
                    },
                }
            )
        if hold:
            ops.append(
                {
                    "operation_id": "hold_sample",
                    "operation_type": "hold_sample",
                    "inputs": {"player_ids": list(player_ids)},
                    "parameters": {
                        "semantics": self.pose_semantics.get(
                            "hold_sample",
                            "freeze the referenced player at its current sample time",
                        ),
                    },
                }
            )
        return ops

    def _update_mode(self, speed: float, prev_speed: float, dt: float, aim_delta: float) -> None:
        thr = self.thresholds
        idle_max = float(thr.get("idle_max_cm_s", 20.0))
        stop_done = float(thr.get("stop_done_cm_s", 8.0))
        cycle_enter = float(thr.get("cycle_enter_cm_s", 120.0))
        stop_enter = float(thr.get("stop_enter_cm_s", 150.0))
        turn_max = float(thr.get("turn_max_cm_s", 40.0))
        turn_exit = float(thr.get("turn_exit_cm_s", 60.0))
        pivot_min = float(thr.get("pivot_min_cm_s", 150.0))
        pivot_angle = float(thr.get("pivot_angle_degrees", 60.0))
        aim_deadzone = float(thr.get("aim_yaw_deadzone_degrees", 15.0))
        accel_resume = float(thr.get("accel_resume_cm_s2", 20.0))
        decel_slope = float(thr.get("decel_slope_cm_s2", 80.0))

        dv_dt = (speed - prev_speed) / dt if dt > 0.0 else 0.0

        if self.mode == "turn":
            if self.turn_state is None:
                self.mode = "idle"
            elif speed > turn_exit:
                self.turn_state = None
                self.mode = "start" if speed > idle_max else "idle"
            return

        if speed <= idle_max:
            if self.mode in ("start", "cycle", "stop", "pivot"):
                if speed <= stop_done:
                    self.mode = "idle"
                else:
                    self.mode = "stop"
            elif self.mode == "idle":
                if abs(aim_delta) > aim_deadzone and speed <= turn_max:
                    self.mode = "turn"
                    self.turn_state = {"remaining": aim_delta}
            return

        if self.mode in ("idle", "turn"):
            self.mode = "start"
            return
        if self.mode == "stop":
            if dv_dt > accel_resume:
                self.mode = "start"
            return
        if self.mode == "start":
            if speed >= cycle_enter:
                self.mode = "cycle"
            return
        if self.mode == "cycle":
            if abs(aim_delta) > pivot_angle and speed > pivot_min:
                self.mode = "pivot"
                self.pivot_elapsed = 0.0
                self.pivot_asset_id = None
            elif dv_dt < -decel_slope and speed <= stop_enter:
                self.mode = "stop"
            return
        if self.mode == "pivot":
            pivot_dur = float(self.playback.get("pivot_seconds", 0.45))
            if self.pivot_elapsed >= pivot_dur:
                self.mode = "cycle"
                self.pivot_asset_id = None
            return

    def _plan_idle(self, dt, aim_delta):
        players = []
        if self.hold_asset_id is None or not self._is_ready(self.hold_asset_id):
            self.hold_asset_id = "motion_03"
            self.hold_sample_time = self._duration("motion_03")
        self.sample_times[self.hold_asset_id] = self.hold_sample_time
        players.append(self._player(self.hold_asset_id, 1.0, 0.0, loop=False))

        idle_asset = "motion_37"
        if idle_asset in self.asset_map:
            players.append(self._player(idle_asset, 0.0, 0.0, loop=True))
            self.deferred_deps.append(idle_asset)

        self.deferred_deps = sorted(set(self.deferred_deps))
        ops = self._pose_operations([f"player_{self.hold_asset_id}"], aim_delta, hold=True)
        return players, [f"player_{self.hold_asset_id}"]

    def _play_rate_for_speed(self, cycle_asset, speed):
        avg = self._avg_speed(cycle_asset)
        if avg <= 0.0:
            return 1.0
        rate = speed / avg
        lo = float(self.playback.get("min_play_rate", 0.05))
        hi = float(self.playback.get("max_play_rate", 2.0))
        return max(lo, min(hi, rate))

    def _plan_start(self, dt, speed, mix, direction):
        gait = self._dominant_gait(mix)
        start_asset = self._start_asset(gait, direction)
        players = []
        members = []

        if self._is_ready(start_asset):
            self._advance(start_asset, dt, 1.0, loop=False)
            players.append(self._player(start_asset, 1.0, 1.0, loop=False))
            members.append(f"player_{start_asset}")
            if self.sample_times[start_asset] >= self._duration(start_asset):
                self.mode = "cycle"
        else:
            self.deferred_deps.append(start_asset)
            players.append(self._player(start_asset, 0.0, 1.0, loop=False))
            cycle = self._cycle_asset(gait, direction)
            ramp = float(self.playback.get("start_ramp_seconds", 0.5))
            progress = min(1.0, self.mode_elapsed / ramp) if ramp > 0.0 else 1.0
            play_rate = self._play_rate_for_speed(cycle, speed)
            self._advance(cycle, dt, play_rate, loop=True)
            players.append(self._player(cycle, progress, play_rate, loop=True))
            members.append(f"player_{cycle}")
        return players, members

    def _plan_cycle(self, dt, speed, mix, direction):
        players = []
        members = []
        walk = self._cycle_asset("walk", direction)
        jog = self._cycle_asset("jog", direction)

        if mix <= 0.0:
            rate = self._play_rate_for_speed(walk, speed)
            self._advance(walk, dt, rate, loop=True)
            players.append(self._player(walk, 1.0, rate, loop=True))
            members.append(f"player_{walk}")
        elif mix >= 1.0:
            rate = self._play_rate_for_speed(jog, speed)
            self._advance(jog, dt, rate, loop=True)
            players.append(self._player(jog, 1.0, rate, loop=True))
            members.append(f"player_{jog}")
        else:
            walk_rate = self._play_rate_for_speed(walk, speed)
            jog_rate = self._play_rate_for_speed(jog, speed)
            self._advance(walk, dt, walk_rate, loop=True)
            self._advance(jog, dt, jog_rate, loop=True)
            players.append(self._player(walk, 1.0 - mix, walk_rate, loop=True))
            players.append(self._player(jog, mix, jog_rate, loop=True))
            members.append(f"player_{walk}")
            members.append(f"player_{jog}")
        return players, members

    def _plan_stop(self, dt, speed, mix, direction):
        gait = self._dominant_gait(mix)
        stop_asset = self._stop_asset(gait, direction)
        players = []
        members = []

        if self._is_ready(stop_asset):
            self._advance(stop_asset, dt, 1.0, loop=False)
            players.append(self._player(stop_asset, 1.0, 1.0, loop=False))
            members.append(f"player_{stop_asset}")
            if self.sample_times[stop_asset] >= self._duration(stop_asset):
                self.hold_asset_id = stop_asset
                self.hold_sample_time = self._duration(stop_asset)
                self.mode = "idle"
        else:
            self.deferred_deps.append(stop_asset)
            players.append(self._player(stop_asset, 0.0, 1.0, loop=False))
            cycle = self._cycle_asset(gait, direction)
            rate = self._play_rate_for_speed(cycle, speed)
            self._advance(cycle, dt, rate, loop=True)
            players.append(self._player(cycle, 1.0, rate, loop=True))
            members.append(f"player_{cycle}")
        return players, members

    def _plan_pivot(self, dt, mix, direction):
        gait = self._dominant_gait(mix)
        desired = self._pivot_asset(gait, direction)
        players = []
        members = []

        pivot = desired if self._is_ready(desired) else "motion_20"
        if pivot != desired:
            self.deferred_deps.append(desired)
            players.append(self._player(desired, 0.0, 1.0, loop=False))
        if not self._is_ready(pivot):
            pivot = "motion_20"

        self._advance(pivot, dt, 1.0, loop=False)
        players.append(self._player(pivot, 1.0, 1.0, loop=False))
        members.append(f"player_{pivot}")
        self.pivot_elapsed += dt
        if self.pivot_elapsed >= float(self.playback.get("pivot_seconds", 0.45)):
            self.mode = "cycle"
        return players, members

    def _plan_turn(self, dt):
        players = []
        members = []
        if self.turn_state is None:
            self.mode = "idle"
            return players, members

        remaining = self.turn_state.get("remaining", 0.0)
        asset_id = self._turn_asset(remaining)
        self._advance(asset_id, dt, 1.0, loop=False)
        players.append(self._player(asset_id, 1.0, 1.0, loop=False))
        members.append(f"player_{asset_id}")

        if asset_id == "turn_left_180_reverse":
            players.append(self._player("motion_34", 0.0, 1.0, loop=False))
            self.deferred_deps.append("motion_34")
        elif asset_id == "turn_right_90_reverse":
            players.append(self._player("motion_35", 0.0, 1.0, loop=False))
            self.deferred_deps.append("motion_35")

        if self.sample_times[asset_id] >= self._duration(asset_id):
            arc = self._turn_arc_degrees(asset_id)
            new_remaining = remaining - arc
            if abs(_wrap180(new_remaining)) > float(
                self.thresholds.get("aim_yaw_deadzone_degrees", 15.0)
            ):
                self.turn_state = {"remaining": new_remaining}
            else:
                self.turn_state = None
                self.mode = "idle"
        return players, members

    def step(self, frame: dict) -> dict:
        dt, velocity, _acceleration, actor_yaw, aim_yaw = self._validate_frame(frame)

        speed = math.hypot(velocity[0], velocity[1])
        prev_speed = math.hypot(self.last_velocity[0], self.last_velocity[1])
        aim_delta = _wrap180(aim_yaw - actor_yaw)

        lx, ly = self._rotate_to_local(velocity, actor_yaw)
        direction = self._direction_from_local(lx, ly, speed)
        self.direction = direction
        gait_mix = self._gait_mix(speed)
        self.gait = self._dominant_gait(gait_mix)

        alpha = float(self.playback.get("velocity_alpha", 0.2))
        self.smoothed_velocity = [
            alpha * velocity[i] + (1.0 - alpha) * self.smoothed_velocity[i] for i in range(3)
        ]

        self._update_mode(speed, prev_speed, dt, aim_delta)

        if self.mode == "idle":
            players, members = self._plan_idle(dt, aim_delta)
        elif self.mode == "start":
            players, members = self._plan_start(dt, speed, gait_mix, direction)
        elif self.mode == "cycle":
            players, members = self._plan_cycle(dt, speed, gait_mix, direction)
        elif self.mode == "stop":
            players, members = self._plan_stop(dt, speed, gait_mix, direction)
        elif self.mode == "pivot":
            players, members = self._plan_pivot(dt, gait_mix, direction)
        elif self.mode == "turn":
            players, members = self._plan_turn(dt)
        else:
            players, members = self._plan_idle(dt, aim_delta)

        sync_groups = self._sync_groups_for(members)
        active_ids = [p["player_id"] for p in players if p.get("weight", 0.0) > 0.0]
        ops = self._pose_operations(active_ids, aim_delta, hold=(self.mode == "idle"))

        plan = {
            "schema_version": _SCHEMA_VERSION,
            "players": players,
            "sync_groups": sync_groups,
            "pose_operations": ops,
            "diagnostics": {
                "mode": self.mode,
                "speed_cm_s": round(speed, 4),
                "gait_mix": round(gait_mix, 4),
                "direction": direction,
                "aim_actor_yaw_delta_degrees": round(aim_delta, 4),
                "clock_seconds": round(self.clock, 6),
                "deferred_missing_samples_dependencies": sorted(set(self.deferred_deps)),
            },
        }

        self.mode_elapsed += dt
        self.clock += dt
        self.last_velocity = list(velocity)
        return plan
