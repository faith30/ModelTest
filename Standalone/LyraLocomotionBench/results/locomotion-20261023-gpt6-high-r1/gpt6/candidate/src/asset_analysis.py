"""Measured contact estimates and loop-window selection for the provided subset.
These are offline heuristics, not mocap contact labels or ground truth.
"""
import math


def quantile(values, q):
    values=sorted(values)
    x=(len(values)-1)*q; i=int(x); a=x-i
    return values[i]*(1-a)+values[min(i+1,len(values)-1)]*a


def analyze(source, data, semantic):
    bones=source['bones']; frames=source['frames']; ts=data['sample_times_seconds']
    names=[b['name'] for b in bones]; n=len(frames)
    contacts={}; events={}; features={}
    for side in ('l','r'):
        name='foot_'+side; idx=names.index(name)
        points=[f['positions'][idx] for f in frames]
        heights=[p[2] for p in points]; floor=quantile(heights,.05)
        speed=[]
        for i in range(n):
            lo=max(0,i-1); hi=min(n-1,i+1); dt=ts[hi]-ts[lo]
            speed.append(math.hypot(points[hi][0]-points[lo][0],points[hi][1]-points[lo][1])/dt)
        # Continuous estimates retain ambiguity rather than claiming IK contacts.
        threshold=max(40.,min(140.,data['average_speed_cm_s']*.25))
        weights=[max(0.,min(1.,(floor+7.-h)/5.))*max(0.,min(1.,(threshold*1.5-v)/threshold))
                 for h,v in zip(heights,speed)]
        # Three-sample median rejects single-frame spikes; no assumed source event times.
        filtered=[sorted(weights[max(0,i-1):min(n,i+2)])[len(weights[max(0,i-1):min(n,i+2)])//2] for i in range(n)]
        strike=[]; active=filtered[0]>=.55
        for i in range(1,n):
            if not active and filtered[i]>=.55:
                if not strike or ts[i]-strike[-1]>.15: strike.append(ts[i])
                active=True
            elif active and filtered[i]<.25: active=False
        contacts[name]={'weights':filtered,'height_floor_estimate_cm':floor,
                        'source_space_planar_speed_cm_s':speed,'speed_threshold_cm_s':threshold,
                        'estimated_contact_onsets_seconds':strike}
        events[side]=strike
        features[name]={'relative_positions_cm':[f['positions'][idx] for f in data['frames']]}
    return {'method':'source component XY finite-difference speed plus per-clip low-height quantile; 3-sample median; hysteretic threshold',
            'confidence':'heuristic_only; no ground/collision labels','parameters':{'floor_quantile':.05,'height_full_cm':2.,'height_zero_cm':7.,'on_threshold':.55,'off_threshold':.25,'minimum_event_spacing_seconds':.15},
            'feet':contacts,'foot_features':features}


def select_cycle_window(data, contact):
    """Choose measured L-to-L interval with one R onset and minimal endpoint error.
    Never manufacture marker timestamps. Fallback is the entire sampled range.
    """
    ts=data['sample_times_seconds']; frames=data['frames']
    left=contact['feet']['foot_l']['estimated_contact_onsets_seconds']
    right=contact['feet']['foot_r']['estimated_contact_onsets_seconds']
    candidates=[]
    for a,b in zip(left,left[1:]):
        middle=[r for r in right if a<r<b]
        if len(middle)!=1 or not .3 <= b-a <= 1.6: continue
        i=min(range(len(ts)),key=lambda i:abs(ts[i]-a)); j=min(range(len(ts)),key=lambda i:abs(ts[i]-b))
        error=math.sqrt(sum(sum((x-y)**2 for x,y in zip(p,q)) for p,q in zip(frames[i]['positions'],frames[j]['positions']))/len(frames[i]['positions']))
        candidates.append((error,a,b,middle[0],i,j))
    if not candidates:
        return {'status':'fallback_full_range','start_seconds':0.,'end_seconds':ts[-1],
                'markers':None,'reason':'No complete measured L-R-L onset interval passed duration bounds'}
    error,a,b,r,i,j=min(candidates)
    dots=[abs(sum(x*y for x,y in zip(q1,q2))) for q1,q2 in zip(frames[i]['rotations_xyzw'],frames[j]['rotations_xyzw'])]
    return {'status':'measured_single_stride','start_seconds':a,'end_seconds':b,
            'markers':[{'name':'L','time_seconds':a},{'name':'R','time_seconds':r},{'name':'L','time_seconds':b}],
            'endpoint_position_rms_cm':error,
            'endpoint_rotation_max_degrees':max(math.degrees(2*math.acos(min(1.,d))) for d in dots),
            'candidate_count':len(candidates),'selection':'minimum component position endpoint RMS among complete measured L-R-L intervals; no seam repair'}


def enrich(source, data, semantic):
    contact=analyze(source,data,semantic)
    data['contact_estimates']=contact
    if semantic['action']=='cycle':
        window=select_cycle_window(data,contact)
        data['cycle_window']=window
        data['loop_range_seconds']=[window['start_seconds'],window['end_seconds']]
        data['cycle_duration_seconds']=window['end_seconds']-window['start_seconds']
        ts=data['sample_times_seconds']; ds=data['distance_cm']
        i=min(range(len(ts)),key=lambda i:abs(ts[i]-window['start_seconds']))
        j=min(range(len(ts)),key=lambda i:abs(ts[i]-window['end_seconds']))
        data['cycle_distance_cm']=ds[j]-ds[i]
        data['cycle_average_speed_cm_s']=data['cycle_distance_cm']/data['cycle_duration_seconds']
    if semantic['action']=='pivot':
        # Point of maximum displacement along incoming motion; retained as measured hint.
        path=data['root_trajectory_cm']; origin=path[0]
        delta=next((p for p in path[1:] if math.hypot(p[0]-origin[0],p[1]-origin[1])>1.),None)
        if delta:
            norm=math.hypot(delta[0]-origin[0],delta[1]-origin[1]); d=[(delta[k]-origin[k])/norm for k in range(2)]
            projections=[sum((p[k]-origin[k])*d[k] for k in range(2)) for p in path]
            i=max(range(len(path)),key=lambda i:projections[i])
            data['pivot_reversal_hint']={'time_seconds':data['sample_times_seconds'][i],
                                        'method':'maximum root displacement projected onto first >1cm incoming displacement',
                                        'not_a_foot_contact_label':True}
    return data
