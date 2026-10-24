from pathlib import Path
p = Path("src/controller.py"); s = p.read_text(encoding="utf-8")
s = s.replace('''            "actor_yaw_delta": dyaw, "velocity": vel, "acceleration": acc,
        }''', '''            "actor_yaw_delta": dyaw, "velocity": vel, "acceleration": acc,
            "accel_local_angle": math.degrees(math.atan2(la[1], la[0])) if has_accel else None,
        }''')
old = '''            v = k["velocity"]
            self.pivot_entry_dir'''
new = '''            data = self.asset_data(aid)
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
            self.pivot_entry_dir'''
assert old in s; s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
g = Path("config/animation_graph.json"); t = g.read_text(encoding="utf-8")
t = t.replace('"root_yaw_offset_max_deg": 120.0', '"root_yaw_offset_max_deg": 180.0')
t = t.replace('"pivot_exit_after_pivot_s": 0.25,', '"pivot_exit_after_pivot_s": 0.25,\n  "pivot_exit_direction_tolerance_deg": 60.0,')
g.write_text(t, encoding="utf-8")
