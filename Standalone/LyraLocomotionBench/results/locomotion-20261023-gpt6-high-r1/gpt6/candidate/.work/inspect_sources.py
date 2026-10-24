import json,math
from pathlib import Path
m=json.loads(Path('raw/manifest.json').read_text())
for c in m['clips']:
 if not c['pose_file']: continue
 s=json.loads((Path('raw')/c['pose_file']).read_text()); fs=s['frames']; names=[b['name'] for b in s['bones']]
 r=names.index('root'); l=names.index('foot_l'); rr=names.index('foot_r')
 print(c['clip_id'],c['source_name'],len(fs),'times',fs[0]['time'],fs[-1]['time'],'root',fs[0]['positions'][r],fs[-1]['positions'][r])
 for i in (r,l,rr):
  ps=[f['positions'][i] for f in fs]
  print(' ',names[i],'range',[(round(min(p[k] for p in ps),2),round(max(p[k] for p in ps),2)) for k in range(3)],'q',fs[0]['rotations_xyzw'][i],fs[-1]['rotations_xyzw'][i])
