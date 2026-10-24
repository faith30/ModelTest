
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
