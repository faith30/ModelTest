"""Final workspace-only inventory and reproducibility check."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

required=['src/build_assets.py','src/controller.py','assets/authored_assets.json','config/animation_graph.json','IMPLEMENTATION.md']
for name in required:
    assert Path(name).is_file() and Path(name).stat().st_size>0
base_env=dict(os.environ, PYTHONPYCACHEPREFIX=str(Path('.tmp/pycache').resolve()))
digests=[]
for seed in ('1','98765'):
    env=dict(base_env,PYTHONHASHSEED=seed)
    digests.append(subprocess.check_output([sys.executable,'.work/determinism_probe.py'],env=env,text=True).strip())
assert digests[0]==digests[1]
subprocess.run([sys.executable,'src/build_assets.py','--manifest','raw/manifest.json','--output','.tmp/rebuilt_assets.json'],env=base_env,check=True)
assert Path('assets/authored_assets.json').read_bytes()==Path('.tmp/rebuilt_assets.json').read_bytes()
report=json.loads(Path('SELF_CHECK.json').read_text())
report['reproducibility']={'independent_process_hash_seeds':[1,98765],'900_frame_plan_sha256':digests[0],'cli_rebuild_byte_identical':True}
report['delivery_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in required+['src/asset_analysis.py']}
Path('SELF_CHECK.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
# Historical edit helpers are not public build steps; remove them to avoid accidental reapplication.
for name in ['enrich_build.py','make_graph.py','refine_controller.py','fix_edges.py','fix_braking.py','extend_checks.py','finalize_config.py']:
    (Path('.work')/name).unlink(missing_ok=True)
if Path('src/__pycache__').exists(): shutil.rmtree('src/__pycache__')
print('Final required files present; checks passed; inventory recorded in SELF_CHECK.json')
