"""Deterministic source-sample authoring; no UE or third-party dependencies."""
import argparse
import hashlib
import json
import math
from pathlib import Path
try:
    from .asset_analysis import enrich
except ImportError:
    from asset_analysis import enrich


def mul(a, b):
    x,y,z,w = a; X,Y,Z,W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def inv(q):
    return [-q[0], -q[1], -q[2], q[3]]


def unit(q):
    n = math.sqrt(sum(x*x for x in q))
    if not math.isfinite(n) or n < 1e-8:
        raise ValueError('Invalid source quaternion')
    return [x/n for x in q]


def yaw(q):
    x,y,z,w = q
    return math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))


def rotate_z(p, a):
    c,s = math.cos(a),math.sin(a)
    return [c*p[0]-s*p[1], s*p[0]+c*p[1], p[2]]


def basis(p):
    return [p[1], -p[0], p[2]]


def process(clip, source):
    bones = source['bones']; frames = source['frames']
    if len(frames) < 2 or len(bones) != clip['pose_bone_count']:
        raise ValueError('Invalid source dimensions')
    root = next(i for i,b in enumerate(bones) if b['name'] == 'root')
    B = [0,0,-math.sqrt(.5),math.sqrt(.5)]
    times=[]; poses=[]; trajectory=[]; distance=[]; yaws=[]
    previous_q=None; prev_angle=None; angle=0.; total=0.
    origin=basis(frames[0]['positions'][root]); t0=frames[0]['time']
    for f in frames:
        t=f['time']-t0
        if times and t <= times[-1]:
            raise ValueError('Nonmonotonic source time')
        if len(f['positions']) != len(bones) or len(f['rotations_xyzw']) != len(bones):
            raise ValueError('Invalid frame dimensions')
        ps=[basis(p) for p in f['positions']]
        qs=[unit(mul(mul(B,unit(q)),inv(B))) for q in f['rotations_xyzw']]
        a=yaw(qs[root])
        if prev_angle is not None:
            angle += (a-prev_angle+math.pi)%(2*math.pi)-math.pi
        prev_angle=a
        delta=[ps[root][k]-origin[k] for k in range(3)]
        if trajectory:
            total += math.hypot(delta[0]-trajectory[-1][0],delta[1]-trajectory[-1][1])
        remove=[0,0,math.sin(-angle/2),math.cos(-angle/2)]
        outp=[rotate_z([p[0]-ps[root][0],p[1]-ps[root][1],p[2]],-angle) for p in ps]
        outq=[unit(mul(remove,q)) for q in qs]
        if previous_q is not None:
            outq=[[-v for v in q] if sum(v*w for v,w in zip(q,old))<0 else q
                  for q,old in zip(outq,previous_q)]
        previous_q=outq
        times.append(t); trajectory.append(delta); distance.append(total); yaws.append(math.degrees(angle))
        poses.append({'time':t,'positions':outp,'rotations_xyzw':outq})
    duration=times[-1]
    return {'duration_seconds':duration,'time_origin_source_seconds':t0,
            'sample_times_seconds':times,'frames':poses,
            'pose_space':'component_actor_basis_in_place',
            'root_trajectory_cm':trajectory,'root_yaw_degrees':yaws,
            'distance_cm':distance,'remaining_distance_cm':[total-d for d in distance],
            'average_speed_cm_s':total/duration,
            'loop_range_seconds':[0,duration] if clip['semantic']['action']=='cycle' else None,
            'source_frame_count':len(frames)}


def build_assets(manifest: dict, manifest_dir: Path) -> dict:
    assets=[]; skeleton=None
    for clip in manifest['clips']:
        recipe={'version':1,'operations':[
            'Read component-space samples; preserve all source times with first time as zero',
            'Re-express positions with B=(y,-x,z), rotations as B*q*inverse(B)',
            'Extract planar root path and unwrapped relative root yaw',
            'Remove current root XY and relative root yaw from every component transform; retain vertical motion',
            'Normalize quaternions and enforce temporal hemisphere continuity',
            'Compute cumulative XY arc length and remaining distance from measured samples',
            'Estimate foot contacts from measured source-space speeds and low foot heights (heuristic, not ground truth)',
            'For cycles select a measured L-R-L single-stride loop window by endpoint position RMS; retain full processed frames',
            'For pivots derive reversal hint from maximum incoming-axis root displacement'],
            'contact_recipe':{'floor_quantile':.05,'height_full_cm':2.,'height_zero_cm':7.,'speed_threshold':'clamp(average_root_speed*0.25,40,140) cm/s','median_samples':3,'on_threshold':.55,'off_threshold':.25},
            'cycle_window_recipe':{'duration_bounds_seconds':[.3,1.6],'required_onsets':['L','R','L'],'fallback':'full source time range, no fabricated markers'},
            'interpolation':{'positions':'linear','rotations':'shortest_arc_slerp','curves':'linear'},
            'root_motion_policy':'in_place; gameplay owns world translation and actor yaw',
            'missing_input_policy':'run identical process() after source samples arrive; do not synthesize poses'}
        entry={'asset_id':'auth_'+clip['clip_id'],'source_clip_ids':[clip['clip_id']],
               'source_name':clip['source_name'],'semantic':clip['semantic'],
               'status':'deferred_missing_samples','recipe':recipe,'data':None}
        if clip['availability']=='pose_samples':
            if not clip['pose_file']:
                raise ValueError('Sampled clip has no pose file')
            path=(manifest_dir/clip['pose_file']).resolve()
            path.relative_to(manifest_dir.resolve())
            raw=path.read_bytes(); source=json.loads(raw.decode('utf-8-sig'))
            if source['clip_id'] != clip['clip_id']:
                raise ValueError('Source identity mismatch')
            if skeleton is None:
                skeleton={'scope':'provided 26-bone subset only; not full Manny or a bind pose',
                          'bones':source['bones'],'source_clip_ids':[]}
            if skeleton['bones'] != source['bones']:
                raise ValueError('Incompatible sampled skeletons')
            skeleton['source_clip_ids'].append(clip['clip_id'])
            entry['data']=enrich(source,process(clip,source),clip['semantic'])
            entry['source_pose_file']=clip['pose_file']; entry['source_sha256']=hashlib.sha256(raw).hexdigest()
            entry['status']='ready'
        else:
            entry['missing_inputs']=[{'clip_id':clip['clip_id'],'required':'component-space pose samples and timestamps'}]
        assets.append(entry)
    return {'schema_version':1,'status':'authored_with_deferred_inputs',
            'source_manifest':{'file':'manifest.json','resolution':'relative to build manifest_dir',
                'sha256_canonical':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()},
            'coordinate_conversion':{'source_to_actor_matrix':[[0,1,0],[-1,0,0],[0,0,1]],
                'position':'B*p','rotation':'B*q*inverse(B); bone local axes are re-expressed too',
                'quaternion':'Hamilton active xyzw','units':'cm, seconds, degrees',
                'root':'planar XY removed; relative yaw removed; Z retained; trajectory is evidence, not gameplay displacement'},
            'skeleton':skeleton,'assets':assets}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    path=args.manifest.resolve()
    result=build_assets(json.loads(path.read_text(encoding='utf-8-sig')),path.parent)
    result['source_manifest']['cli_path']=args.manifest.as_posix()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Built',len(result['assets']),'assets;',sum(a['status']=='ready' for a in result['assets']),'sampled')


if __name__=='__main__':
    main()
