from pathlib import Path
p = Path("src/controller.py"); s = p.read_text(encoding="utf-8")
old = '(v[0] * self.pivot_entry_dir[0] + v[1] * self.pivot_entry_dir[1]) <= 0.0:'
assert old in s
s = s.replace(old, '(v[0] * self.pivot_entry_dir[0] + v[1] * self.pivot_entry_dir[1]) <= 0.1 * k["speed"]:')
p.write_text(s, encoding="utf-8")
g = Path("config/animation_graph.json"); t = g.read_text(encoding="utf-8")
t = t.replace('"pivot_exit_direction_tolerance_deg": 60.0', '"pivot_exit_direction_tolerance_deg": 35.0')
g.write_text(t, encoding="utf-8")
