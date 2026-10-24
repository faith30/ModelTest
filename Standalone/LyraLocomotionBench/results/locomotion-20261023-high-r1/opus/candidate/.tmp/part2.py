
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
                if not self.pivot_reversed and (v[0] * self.pivot_entry_dir[0] + v[1] * self.pivot_entry_dir[1]) <= 0.0:
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
