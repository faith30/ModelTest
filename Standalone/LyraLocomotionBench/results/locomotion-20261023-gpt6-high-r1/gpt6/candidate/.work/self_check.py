"""Local static/data/plan tests only. Run from task workspace root."""
import copy
import hashlib
import json
import math
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from src.build_assets import build_assets, mul, inv, unit
from src.controller import LocomotionController, wrap

ROOT=Path.cwd()
G=json.loads(Path('config/animation_graph.json').read_text(encoding='utf-8'))
A=json.loads(Path('assets/authored_assets.json').read_text(encoding='utf-8'))
M=json.loads(Path('raw/manifest.json').read_text(encoding='utf-8-sig'))
TABLE={a['asset_id']:a for a in A['assets']}
checks=[]; scenarios={}; snapshots={}; frame_count=0


def check(name, f):
    f(); checks.append({'name':name,'status':'passed'})


def frame(v=(0.,0.,0.), a=(0.,0.,0.), actor=0., aim=0., dt=1/60):
    return {'dt_seconds':dt,'velocity_world_cm_s':list(v),'acceleration_world_cm_s2':list(a),
            'actor_yaw_degrees':actor,'aim_yaw_degrees':aim}


def verify(plan):
    global frame_count
    frame_count+=1
    json.dumps(plan,allow_nan=False)
    players=plan['players']; assert players
    ids={p['player_id'] for p in players}; assert len(ids)==len(players)
    assert abs(sum(p['weight'] for p in players)-1)<1e-9
    for p in players:
        assert 0<=p['weight']<=1 and 0<=p['play_rate']<1e6
        asset=TABLE[p['asset_id']]; data=asset['data']
        assert p['availability']==asset['status']
        if not data:
            assert p['sample_time_seconds'] is None and not p['pose_materializable'] and p['play_rate']==0
        else:
            assert -1e-9<=p['sample_time_seconds']<=data['duration_seconds']+1e-9
            if p['player_id'].startswith('cycle_'):
                lo,hi=data['loop_range_seconds']
                assert lo-1e-8<=p['sample_time_seconds']<hi+1e-8
                phase=LocomotionController._time_to_phase(data,p['sample_time_seconds'])
                assert abs(phase-p['normalized_phase'])<1e-8
    for group in plan['sync_groups']:
        assert set(group['member_player_ids'])<=ids
        for p in players:
            if p['player_id'] in group['member_player_ids']:
                assert abs(p['normalized_phase']-group['settings']['phase'])<1e-8
    seen=set(ids)
    for op in plan['pose_operations']:
        assert set(op['inputs'])<=seen
        assert op['operation_id'] not in seen
        seen.add(op['operation_id'])
    feet=plan['pose_operations'][-1]['parameters']
    assert all(-1e-8<=w<=1+1e-8 for w in feet['contact_weights'].values())
    assert abs(feet['sampled_weight_coverage']+feet['unknown_contact_weight']-1)<1e-8


def run(name, frames, controller=None):
    c=controller or LocomotionController(G,A); states=[]; used=set(); plans=[]
    for f in frames:
        p=c.step(f); verify(p); plans.append(p)
        used.update(x['asset_id'] for x in p['players'])
        if not states or states[-1]!=p['diagnostics']['state']: states.append(p['diagnostics']['state'])
    scenarios[name]={'frames':len(plans),'state_sequence':states,'asset_ids':sorted(used)}
    snapshots[name]=plans[-1]
    return c,plans


def assets_test():
    assert len(A['assets'])==37 and len(TABLE)==37
    assert sum(a['status']=='ready' for a in TABLE.values())==15
    assert sum(a['status']=='deferred_missing_samples' for a in TABLE.values())==22
    assert len(A['skeleton']['bones'])==26
    B=[0,0,-math.sqrt(.5),math.sqrt(.5)]
    for clip in M['clips']:
        entry=TABLE['auth_'+clip['clip_id']]
        assert entry['source_clip_ids']==[clip['clip_id']] and entry['recipe']['operations']
        d=entry['data']
        if clip['availability']=='metadata_only':
            assert d is None and entry['missing_inputs']; continue
        path=Path('raw')/clip['pose_file']; raw=path.read_bytes(); source=json.loads(raw)
        assert entry['source_sha256']==hashlib.sha256(raw).hexdigest()
        assert len(d['frames'])==len(source['frames'])
        assert all(b>=a for a,b in zip(d['distance_cm'],d['distance_cm'][1:]))
        assert all(b>a for a,b in zip(d['sample_times_seconds'],d['sample_times_seconds'][1:]))
        for i,f in enumerate(d['frames']):
            assert abs(f['positions'][0][0])+abs(f['positions'][0][1])<1e-7
            for q in f['rotations_xyzw']: assert abs(sum(x*x for x in q)-1)<1e-8
            for pos in f['positions']: assert all(math.isfinite(x) for x in pos)
            # Reconstruct original basis-converted component positions and orientations.
            sf=source['frames'][i]; root=sf['positions'][0]; r=[root[1],-root[0],root[2]]
            yaw=math.radians(d['root_yaw_degrees'][i]); co,si=math.cos(yaw),math.sin(yaw)
            Y=[0,0,math.sin(yaw/2),math.cos(yaw/2)]
            for j,p in enumerate(f['positions']):
                reconstructed=[co*p[0]-si*p[1]+r[0],si*p[0]+co*p[1]+r[1],p[2]]
                original=sf['positions'][j]; expected=[original[1],-original[0],original[2]]
                assert max(abs(x-y) for x,y in zip(reconstructed,expected))<1e-7
                q=mul(Y,f['rotations_xyzw'][j]); expected_q=unit(mul(mul(B,unit(sf['rotations_xyzw'][j])),inv(B)))
                assert abs(abs(sum(x*y for x,y in zip(q,expected_q)))-1)<1e-7
        if clip['semantic']['action']=='cycle':
            window=d['cycle_window']; assert window['status']=='measured_single_stride'
            for marker in window['markers']: assert marker['time_seconds'] in d['sample_times_seconds']
    assert abs(TABLE['auth_motion_33']['data']['root_yaw_degrees'][-1]+90)<.01
    assert abs(TABLE['auth_motion_36']['data']['root_yaw_degrees'][-1]-180)<.01


def deterministic_build():
    built=build_assets(M,ROOT/'raw')
    original=copy.deepcopy(A)
    original['source_manifest'].pop('cli_path',None)
    assert built==original


def cardinals():
    for gait,speed in [('walk',300.),('jog',600.)]:
        for direction,xy in [('fwd',(1,0)),('bwd',(-1,0)),('left',(0,-1)),('right',(0,1))]:
            vel=[speed*xy[0],speed*xy[1],0]
            _,plans=run(gait+'_'+direction,[frame(v=vel) for _ in range(300)])
            last=plans[-1]; assert last['diagnostics']['state']=='cycle'
            wanted=next(a['asset_id'] for a in A['assets'] if a['semantic']=={'gait':gait,'direction':direction,'action':'cycle'})
            assert max(last['players'],key=lambda p:p['weight'])['asset_id']==wanted
            assert any(p['diagnostics']['state']=='start' for p in plans)


def stops_and_restart():
    for speed in (300.,600.):
        seq=[frame(v=(speed,0,0)) for _ in range(180)]
        decel=400. if speed==300 else 900.
        seq += [frame(v=(max(0.,speed-decel*(i+1)/60),0,0),a=(-decel,0,0)) for i in range(math.ceil(speed/decel*60))]
        seq += [frame() for _ in range(180)]
        _,plans=run('stop_'+str(int(speed)),seq)
        assert any(p['diagnostics']['state']=='stop' for p in plans)
        assert plans[-1]['diagnostics']['state']=='idle'
        assert not any(p['diagnostics']['state']=='pivot' for p in plans)
    seq=[frame(v=(300,0,0)) for _ in range(180)]
    seq += [frame(v=(180,0,0),a=(-400,0,0)) for _ in range(5)]
    seq += [frame(v=(250,0,0),a=(600,0,0)) for _ in range(15)]
    _,ps=run('stop_restart',seq)
    assert ps[-1]['diagnostics']['state']=='start'


def pivot_test():
    for direction,xy in [('fwd',(1,0)),('bwd',(-1,0)),('left',(0,-1)),('right',(0,1))]:
        for gait,speed in [('walk',300.),('jog',600.)]:
            seq=[frame(v=(speed*xy[0],speed*xy[1],0)) for _ in range(180)]
            seq += [frame(v=(-speed*xy[0],-speed*xy[1],0)) for _ in range(150)]
            _,ps=run('pivot_'+gait+'_'+direction,seq)
            assert ps[180]['diagnostics']['state']=='pivot'
            action=next(p for p in ps[180]['players'] if TABLE[p['asset_id']]['semantic']['action']=='pivot')
            assert TABLE[action['asset_id']]['semantic']['direction']==direction
            assert ps[-1]['diagnostics']['state']=='cycle'
    _,ps=run('predicted_reversal',[frame(v=(600,0,0)) for _ in range(180)]+[frame(v=(200,0,0),a=(-1800,0,0))])
    assert ps[-1]['diagnostics']['state']=='pivot'


def turns():
    for aim,wanted in [(-90,'auth_motion_33'),(-170,'auth_motion_34'),(90,'auth_motion_35'),(170,'auth_motion_36')]:
        _,ps=run('turn_'+str(aim),[frame(aim=aim) for _ in range(240)])
        assert ps[0]['players'][0]['asset_id']==wanted
        assert ps[-1]['diagnostics']['state']=='idle'
        offset=ps[-1]['pose_operations'][1]['parameters']['yaw_degrees']
        if TABLE[wanted]['data']: assert abs(wrap(offset-aim))<1e-6
        else: assert offset==0 and len([p for p in ps if p['diagnostics']['state']=='turn'])<70
    seq=[frame(aim=-90) for _ in range(20)] + [frame(v=(300,0,0),aim=-90) for _ in range(60)]
    _,ps=run('turn_movement_interrupt',seq)
    assert ps[20]['diagnostics']['state']=='start'
    # Actor follows the same measured source yaw: offset must not apply a second turn.
    c=LocomotionController(G,A); seq=[]
    data=TABLE['auth_motion_33']['data']
    for t,y in zip(data['sample_times_seconds'],data['root_yaw_degrees']):
        seq.append(frame(actor=y,aim=-90))
    _,ps=run('turn_actor_yaw_follow',seq,c)
    assert abs(ps[-1]['pose_operations'][1]['parameters']['yaw_degrees'])<2.
    _,ps=run('yaw_wrap',[frame(actor=179,aim=-179) for _ in range(10)])
    assert all(p['diagnostics']['state']=='idle' for p in ps)


def sync_sweeps():
    seq=[]
    for i in range(1000):
        theta=math.radians(i*.9); speed=425+200*math.sin(i*.013)
        seq.append(frame(v=(speed*math.cos(theta),speed*math.sin(theta),0),actor=30*math.sin(i*.007),aim=0,dt=[1/30,1/60,1/120][i%3]))
    run('direction_gait_sweep',seq)
    # Explicit sync test while a direction's weight fades completely to zero.
    run('orthogonal_switch',[frame(v=(300,0,0)) for _ in range(150)]+[frame(v=(0,300,0)) for _ in range(150)])


def validation_and_reset():
    c=LocomotionController(G,A); good=frame(v=(200,0,0))
    bads=[{},frame(dt=0),frame(dt=-1),frame(dt=float('nan')),frame(v=(float('inf'),0,0)),frame(actor=float('nan')),frame(aim=float('inf')),frame(dt=True),frame(dt=3601),frame(v=(1e300,0,0))]
    b=frame(); b['velocity_world_cm_s']=[0,0]; bads.append(b)
    b=frame(); b['acceleration_world_cm_s2']='bad'; bads.append(b)
    for f in bads:
        before=copy.deepcopy(c.__dict__)
        try: c.step(f)
        except ValueError: pass
        else: raise AssertionError('invalid frame accepted')
        assert before==c.__dict__
    seq=[frame(v=(200,0,0)),frame(v=(500,0,0)),frame(v=(-500,0,0)),frame(),frame(aim=-90)]*40
    one=[c.step(f) for f in seq]; c.reset(seed=0); two=[c.step(f) for f in seq]
    assert one==two
    for p in two: verify(p)
    c1=LocomotionController(G,A); c2=LocomotionController(G,A)
    for _ in range(20):
        a=frame(v=(0,300,0),actor=90,aim=90); b=frame(v=(0,300,0),actor=810,aim=-630)
        assert c1.step(a)==c2.step(b)
    run('large_dt',[frame(dt=10),frame(v=(600,0,0),dt=4),frame(v=(-600,0,0),dt=2),frame(aim=170,dt=8)])


def randomized():
    rng=random.Random(42); seq=[]; v=[0.,0.,0.]; actor=0.
    for i in range(2000):
        dt=rng.choice([1/120,1/60,1/30,.08])
        if i%45==0:
            theta=rng.uniform(-math.pi,math.pi); speed=rng.choice([0,5,20,200,350,450,650])
            new=[speed*math.cos(theta),speed*math.sin(theta),0]
            a=[(new[k]-v[k])/dt for k in range(3)]; v=new
        else: a=[0.,0.,0.]
        actor+=rng.uniform(-1,1)
        seq.append(frame(v,a,actor,actor+70*math.sin(i*.02),dt))
    run('seeded_input_changes',seq)


def abrupt_directional_stops():
    for gait,speed in [('walk',300.),('jog',600.)]:
        for direction,xy in [('fwd',(1,0)),('bwd',(-1,0)),('left',(0,-1)),('right',(0,1))]:
            seq=[frame(v=(xy[0]*speed,xy[1]*speed,0)) for _ in range(180)]
            seq += [frame() for _ in range(180)]
            _,ps=run('abrupt_stop_'+gait+'_'+direction,seq)
            assert ps[180]['diagnostics']['state']=='stop'
            stops=[p for p in ps[180]['players'] if TABLE[p['asset_id']]['semantic']['action']=='stop']
            assert len(stops)==1
            semantic=TABLE[stops[0]['asset_id']]['semantic']
            assert semantic['gait']==gait and semantic['direction']==direction
            assert ps[-1]['diagnostics']['state']=='idle'


def contacts_and_config():
    from src.controller import interpolate
    c,plans=run('diagonal_blend',[frame(v=(300,300,0)) for _ in range(300)])
    p=plans[-1]
    assert p['diagnostics']['state']=='cycle'
    directions={TABLE[x['asset_id']]['semantic']['direction'] for x in p['players']}
    assert directions=={'fwd','right'}
    assert len(p['players'])==4
    for foot in ('foot_l','foot_r'):
        expected=0.
        for player in p['players']:
            data=TABLE[player['asset_id']]['data']
            expected+=player['weight']*interpolate(data['sample_times_seconds'],data['contact_estimates']['feet'][foot]['weights'],player['sample_time_seconds'])
        actual=p['pose_operations'][-1]['parameters']['contact_weights'][foot]
        assert abs(actual-expected)<1e-10
    # Demonstrate graph consumption: changed threshold changes selection, changed binding changes player.
    modified=copy.deepcopy(G); modified['parameters']['turn_enter_degrees']=100.
    c=LocomotionController(modified,A)
    assert c.step(frame(aim=-90))['diagnostics']['state']=='idle'
    modified=copy.deepcopy(G)
    next(n for n in modified['nodes'] if n['id']=='state')['bindings']['walk.fwd.start']='auth_motion_18'
    c=LocomotionController(modified,A)
    assert c.step(frame(v=(300,0,0)))['players'][0]['asset_id']=='auth_motion_18'
    # Stationary acceleration intent selects the right-side start without requiring velocity.
    _,ps=run('stationary_acceleration_intent',[frame(a=(0,1000,0))])
    assert TABLE[ps[0]['players'][0]['asset_id']]['semantic']['direction']=='right'
    # Changing aim back to current facing interrupts rather than completing the obsolete target.
    c=LocomotionController(G,A)
    c.step(frame(aim=-90))
    p=c.step(frame(aim=0)); verify(p)
    assert p['diagnostics']['state']=='idle'


for name,test in [('asset_provenance_and_reconstruction',assets_test),('deterministic_rebuild',deterministic_build),
                  ('eight_cardinal_cycles',cardinals),('eight_abrupt_directional_stops',abrupt_directional_stops),('contacts_and_graph_consumption',contacts_and_config),('stop_and_restart',stops_and_restart),('eight_pivot_bindings',pivot_test),
                  ('turn_signs_deferred_and_actor_authority',turns),('phase_sync_direction_gait',sync_sweeps),
                  ('validation_reset_yaw_equivalence',validation_and_reset),('seeded_changes',randomized)]:
    check(name,test)
report={'status':'passed','scope':'offline data and playback-plan validation only; not rendered pose or UE validation',
        'checks':checks,'validated_plan_frames':frame_count,'asset_counts':{'ready':15,'deferred_missing_samples':22},
        'scenarios':scenarios,'loop_endpoint_measurements':{a['asset_id']:a['data']['cycle_window'] for a in A['assets'] if a['data'] and a['semantic']['action']=='cycle'}}
Path('SELF_CHECK.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
Path('.tmp/plan_snapshots.json').write_text(json.dumps(snapshots,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
print('PASS:',len(checks),'checks;',frame_count,'validated plans;',len(scenarios),'scenarios')
