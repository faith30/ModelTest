"""Print a canonical digest of plans; used with distinct PYTHONHASHSEED values."""
import hashlib
import json
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from src.controller import LocomotionController
c=LocomotionController(json.loads(Path('config/animation_graph.json').read_text()),json.loads(Path('assets/authored_assets.json').read_text()))
h=hashlib.sha256()
for i in range(900):
    angle=i*.019; speed=420+230*math.sin(i*.027)
    plan=c.step({'dt_seconds':1/60,'velocity_world_cm_s':[speed*math.cos(angle),speed*math.sin(angle),0],
                 'acceleration_world_cm_s2':[0,0,0],'actor_yaw_degrees':i*.1,'aim_yaw_degrees':i*.1+80})
    h.update(json.dumps(plan,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
print(h.hexdigest())
