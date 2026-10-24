"""Grounded locomotion playback planner, not a pose evaluator.
All sample clocks are owned here. Configuration is consumed from animation_graph.json.
"""
import bisect
import math


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def wrap(x):
    return (x + 180.) % 360. - 180.


def smooth(old, target, dt, tau):
    return target + (old-target)*math.exp(-dt/max(tau,1e-6))


def interpolate(xs, ys, x):
    if x <= xs[0]: return ys[0]
    if x >= xs[-1]: return ys[-1]
    i=bisect.bisect_right(xs,x)-1
    a=(x-xs[i])/(xs[i+1]-xs[i])
    return ys[i]*(1-a)+ys[i+1]*a


def inverse_distance(data, distance):
    ds=data['distance_cm']; ts=data['sample_times_seconds']
    if distance <= ds[0]: return ts[0]
    if distance >= ds[-1]: return ts[-1]
    i=bisect.bisect_left(ds,distance)
    if ds[i]-ds[i-1] < 1e-9: return ts[i]
    return ts[i-1]+(ts[i]-ts[i-1])*(distance-ds[i-1])/(ds[i]-ds[i-1])


class LocomotionController:
    def __init__(self, graph: dict, assets: dict) -> None:
        if graph.get('schema_version') != 1 or assets.get('schema_version') != 1:
            raise ValueError('Unsupported schema')
        self.graph=graph; self.assets=assets
        self.p=graph['parameters']; self.nodes={n['id']:n for n in graph['nodes']}
        self.bindings=self.nodes['state']['bindings']
        self.table={a['asset_id']:a for a in assets['assets']}
        if len(self.table)!=len(assets['assets']) or len(self.nodes)!=len(graph['nodes']):
            raise ValueError('Duplicate asset or node ID')
        for aid in self.bindings.values():
            if aid not in self.table: raise ValueError('Unresolved asset '+aid)
        for edge in graph['connections']:
            if edge['from'] not in self.nodes or edge['to'] not in self.nodes:
                raise ValueError('Unresolved graph connection')
        if graph['output'] not in self.nodes: raise ValueError('Unresolved output')
        expected_chain=['blend','facing','orientation','stride','lean','feet']
        edges={(e['from'],e['to']) for e in graph['connections']}
        if graph['output']!='feet' or any((a,b) not in edges for a,b in zip(expected_chain,expected_chain[1:])):
            raise ValueError('This planner requires the declared ordered pose-operation chain')
        if self.nodes['cycles']['angles_degrees']!={'fwd':0.,'right':90.,'bwd':180.,'left':270.}:
            raise ValueError('Cycle node requires cardinal actor-space angles')
        self.angles=self.nodes['cycles']['angles_degrees']
        self.group_id=self.nodes['cycles']['sync_group']
        self.group_config=next(g for g in graph['sync_groups'] if g['group_id']==self.group_id)
        self.reset()

    def reset(self, seed: int = 0) -> None:
        self.state='idle'; self.state_age=0.; self.gait='walk'; self.jog_alpha=0.
        self.phase=0.; self.direction=0.; self.direction_name='fwd'
        self.prev_velocity=None; self.prev_actor=None; self.visual_yaw=None
        self.action=None; self.serial=0; self.weights={}; self.players={}
        self.pivot_cooldown=0.; self.turn_cooldown=0.; self.pivot_latched=False
        self.last_missing_turn_aim=None; self.lean=[0.,0.]; self.total_time=0.
        self.last_transition=None; self.seed=seed

    def validate(self, frame):
        def number(v, name):
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
                raise ValueError(name+' must be a finite number')
            return float(v)
        try:
            dt=number(frame['dt_seconds'],'dt_seconds')
            if dt<=0: raise ValueError('dt_seconds must be positive')
            # Finite domain extremes use a documented rejection policy, not overflow.
            if dt>self.p['input_bounds']['dt_max_seconds']: raise ValueError('dt_seconds exceeds configured bound')
            vectors=[]
            for key in ('velocity_world_cm_s','acceleration_world_cm_s2'):
                v=frame[key]
                if not isinstance(v,(list,tuple)) or len(v)!=3:
                    raise ValueError(key+' must contain three numbers')
                vector=[number(x,key) for x in v]
                if any(abs(x)>self.p['input_bounds']['vector_component_abs_max'] for x in vector):
                    raise ValueError(key+' exceeds configured magnitude bound')
                vectors.append(vector)
            actor=wrap(number(frame['actor_yaw_degrees'],'actor_yaw_degrees'))
            aim=wrap(number(frame['aim_yaw_degrees'],'aim_yaw_degrees'))
        except (KeyError,TypeError) as e:
            raise ValueError('Missing or invalid frame field: '+str(e)) from e
        return dt,vectors[0],vectors[1],actor,aim

    def _asset(self, gait, direction, action):
        return self.bindings[f'{gait}.{direction}.{action}']

    def _nearest_direction(self, angle, previous=None):
        closest=min(self.angles,key=lambda k:abs(wrap(angle-self.angles[k])))
        if previous and abs(wrap(angle-self.angles[previous])) <= 45+self.p['direction_hysteresis_degrees']:
            return previous
        return closest

    def _align_phase_from_action(self):
        if not self.action: return
        data=self.table[self.action['asset_id']]['data']
        cycle=self.table[self._asset(self.gait,self.direction_name,'cycle')]['data']
        if not data or not cycle: return
        # Match the two measured component-space feet at handoff; no synthetic markers.
        t=self.action['time']; times=data['sample_times_seconds']
        foot_data=data['contact_estimates']['foot_features']
        current=[]
        for foot in ('foot_l','foot_r'):
            points=foot_data[foot]['relative_positions_cm']
            current.extend(interpolate(times,[p[k] for p in points],t) for k in range(3))
        lo,hi=cycle['loop_range_seconds']; candidates=[]
        for i,ct in enumerate(cycle['sample_times_seconds']):
            if not lo<=ct<hi: continue
            sample=[]
            for foot in ('foot_l','foot_r'):
                sample.extend(cycle['contact_estimates']['foot_features'][foot]['relative_positions_cm'][i])
            error=sum((x-y)**2 for x,y in zip(current,sample))
            candidates.append((error,ct))
        if candidates:
            self.phase=self._time_to_phase(cycle,min(candidates)[1])

    @staticmethod
    def _phase_to_time(data, phase):
        lo,hi=data['loop_range_seconds']; markers=data.get('cycle_window',{}).get('markers')
        if markers:
            middle=markers[1]['time_seconds']
            if phase<.5: return lo+2*phase*(middle-lo),2*(middle-lo)
            return middle+2*(phase-.5)*(hi-middle),2*(hi-middle)
        return lo+phase*(hi-lo),hi-lo

    @staticmethod
    def _time_to_phase(data, time):
        lo,hi=data['loop_range_seconds']; markers=data.get('cycle_window',{}).get('markers')
        if markers:
            middle=markers[1]['time_seconds']
            return .5*(time-lo)/(middle-lo) if time<middle else .5+.5*(time-middle)/(hi-middle)
        return (time-lo)/(hi-lo)

    def _enter(self, state, direction=None, aim=None, turn_delta=None, action_gait=None):
        if state=='cycle': self._align_phase_from_action()
        old=self.state; self.state=state; self.state_age=0.; self.action=None
        self.last_transition={'from':old,'to':state,'at_seconds':self.total_time}
        if old=='pivot': self.pivot_cooldown=self.p['pivot_cooldown_seconds']
        if old=='turn': self.turn_cooldown=self.p['turn_cooldown_seconds']
        if state in ('idle','cycle'): return
        self.serial+=1
        if state=='turn':
            size=180 if abs(turn_delta)>=self.p['turn_180_threshold_degrees'] else 90
            anatomical=size if turn_delta<0 else -size
            aid=self.bindings[f'turn.{anatomical}']
            scale=clamp(abs(turn_delta)/size,.75,1.25)
        else:
            aid=self._asset(action_gait or self.gait,direction or self.direction_name,state); scale=1.
        self.action={'asset_id':aid,'player_id':f'action_{self.serial}', 'time':0.,'travel':0.,
                     'yaw_applied':0.,'yaw_scale':scale,'direction':direction or self.direction_name,
                     'aim_at_entry':aim,'complete':False,'gait_at_entry':action_gait or self.gait,
                     'entry_warp_degrees':clamp(wrap(self.direction-self.angles[direction or self.direction_name]),-self.p['orientation_warp_limit_degrees'],self.p['orientation_warp_limit_degrees'])}

    def _cycle_targets(self, speed, dt):
        angle=self.direction%360.; order=sorted(self.angles,key=self.angles.get)
        # Four evenly spaced cardinal directions are part of this node's contract.
        sector=int(angle//90); f=(angle%90)/90
        directional={order[sector]:1-f, order[(sector+1)%4]:f}
        targets={}; phase_speed=0.; entries=[]
        for gait,gw in [('walk',1-self.jog_alpha),('jog',self.jog_alpha)]:
            for direction,dw in directional.items():
                w=gw*dw
                if w < 1e-8: continue
                aid=self._asset(gait,direction,'cycle'); data=self.table[aid]['data']
                if data:
                    nominal=max(data.get('cycle_average_speed_cm_s',data['average_speed_cm_s']),1e-6)
                    rate=clamp(speed/nominal,self.p['play_rate_min'],self.p['play_rate_max'])
                    freq=rate/data.get('cycle_duration_seconds',data['duration_seconds'])
                else: freq=0.
                phase_speed+=w*freq
                entries.append((aid,w))
        self.phase=(self.phase+dt*phase_speed)%1.
        # Fading-out cycles remain genuine followers, including zero-target directions.
        for player in self.players.values():
            if not player['player_id'].startswith('cycle_'): continue
            data=self.table[player['asset_id']]['data']
            if data:
                sample,derivative=self._phase_to_time(data,self.phase)
                player['sample_time_seconds']=sample
                player['play_rate']=phase_speed*derivative
                player['normalized_phase']=self.phase
        for aid,w in entries:
            data=self.table[aid]['data']
            sample,derivative=self._phase_to_time(data,self.phase) if data else (None,0.)
            pid='cycle_'+aid
            self.players[pid]={'player_id':pid,'asset_id':aid,'sample_time_seconds':sample,
                               'play_rate':phase_speed*derivative,'loop':True,
                               'normalized_phase':self.phase,'clock':'shared_contact_phase',
                               'loop_range_seconds':data['loop_range_seconds'] if data else None}
            targets[pid]=w
        return targets

    def _advance_action(self, speed, decel, dt):
        act=self.action; asset=self.table[act['asset_id']]; data=asset['data']
        previous=act['time']; rate=1.
        if data:
            duration=data['duration_seconds']; target=previous+dt
            if self.state=='start':
                act['travel']+=speed*dt
                target=inverse_distance(data,act['travel'])
            elif self.state=='stop':
                # Constant-deceleration estimate, not a collision-aware world stop point.
                remaining=speed*speed/(2*max(decel,self.p['default_braking_cm_s2'] if decel<1 else decel))
                target=inverse_distance(data,max(0.,data['distance_cm'][-1]-remaining))
            elif self.state=='pivot':
                target=previous+dt*clamp(speed/max(data['average_speed_cm_s'],1.),.75,1.35)
            if self.state in ('start','stop'):
                target=clamp(target,previous+dt*self.p['distance_match_min_rate'],previous+dt*self.p['distance_match_max_rate'])
            act['time']=clamp(target,previous,duration)
            rate=(act['time']-previous)/dt
            act['complete']=act['time']>=duration-1e-7
            if self.state=='turn':
                y=interpolate(data['sample_times_seconds'],data['root_yaw_degrees'],act['time'])*act['yaw_scale']
                self.visual_yaw=wrap(self.visual_yaw+y-act['yaw_applied']); act['yaw_applied']=y
            sample=act['time']
        else:
            act['complete']=self.state_age>=self.p['deferred_action_policy_seconds'][self.state]
            sample=None; rate=0.
        pid=act['player_id']
        self.players[pid]={'player_id':pid,'asset_id':act['asset_id'],'sample_time_seconds':sample,
                           'play_rate':rate,'loop':False,'clock':'distance_bounded' if self.state in ('start','stop') else 'one_shot',
                           'progress_basis':'measured_clip_time' if data else 'policy_timer_only_not_clip_progress',
                           'policy_elapsed_seconds':self.state_age}
        return {pid:1.}

    def step(self, frame: dict) -> dict:
        dt,v,a,actor,aim=self.validate(frame)  # Validate before mutating any state.
        p=self.p; incoming_gait=self.gait; self.total_time+=dt; self.state_age+=dt
        self.pivot_cooldown=max(0.,self.pivot_cooldown-dt)
        self.turn_cooldown=max(0.,self.turn_cooldown-dt)
        speed=math.hypot(v[0],v[1]); acceleration=math.hypot(a[0],a[1])
        if not math.isfinite(speed) or not math.isfinite(acceleration):
            raise ValueError('Input magnitude overflow')
        r=math.radians(actor); c,s=math.cos(r),math.sin(r)
        local_v=[c*v[0]+s*v[1],-s*v[0]+c*v[1]]
        local_a=[c*a[0]+s*a[1],-s*a[0]+c*a[1]]
        if self.visual_yaw is None: self.visual_yaw=actor
        intent=acceleration>=p['intent_acceleration_cm_s2']
        moving=speed>=p['move_enter_cm_s']; stopped=speed<=p['move_exit_cm_s']
        predicted=math.hypot(v[0]+a[0]*p['prediction_seconds'],v[1]+a[1]*p['prediction_seconds'])
        gait_speed=max(speed,predicted) if self.state in ('idle','start') else speed
        if self.gait=='walk' and gait_speed>=p['jog_enter_cm_s']: self.gait='jog'
        if self.gait=='jog' and gait_speed<=p['jog_exit_cm_s']: self.gait='walk'
        alpha=clamp((speed-p['walk_to_jog_low_cm_s'])/(p['walk_to_jog_high_cm_s']-p['walk_to_jog_low_cm_s']),0.,1.)
        self.jog_alpha=smooth(self.jog_alpha,alpha,dt,p['gait_smoothing_seconds'])
        raw_direction=math.degrees(math.atan2(local_v[1],local_v[0])) if speed>p['move_exit_cm_s'] else (
            math.degrees(math.atan2(local_a[1],local_a[0])) if intent else self.direction)
        if self.prev_velocity is None or (self.state=='idle' and (moving or intent)):
            self.direction=raw_direction
        else:
            self.direction=wrap(self.direction+wrap(raw_direction-self.direction)*(1-math.exp(-dt/p['direction_smoothing_seconds'])))
        self.direction_name=self._nearest_direction(raw_direction,self.direction_name)
        dot=(v[0]*a[0]+v[1]*a[1])/max(speed,1e-8)
        decel=max(0.,-dot)
        braking=decel>=p['braking_acceleration_cm_s2']
        oppose=dot/max(acceleration,1e-8)
        if oppose>-.2 or stopped: self.pivot_latched=False
        desired=[v[k]+a[k]*p['prediction_seconds'] for k in range(2)]
        desired_len=math.hypot(*desired)
        pred_dot=(v[0]*desired[0]+v[1]*desired[1])/max(speed*desired_len,1e-8)
        observed_reversal=False; incoming=self.direction_name
        if self.prev_velocity is not None:
            prev_speed=math.hypot(*self.prev_velocity)
            if prev_speed>=p['pivot_min_speed_cm_s'] and speed>=p['move_enter_cm_s']:
                cos=(v[0]*self.prev_velocity[0]+v[1]*self.prev_velocity[1])/(speed*prev_speed)
                observed_reversal=cos<=math.cos(math.radians(p['pivot_angle_degrees']))
                if observed_reversal:
                    pv=self.prev_velocity
                    incoming=self._nearest_direction(math.degrees(math.atan2(-s*pv[0]+c*pv[1],c*pv[0]+s*pv[1])))
        pivot=(observed_reversal or (self.state in ('start','cycle') and speed>=p['pivot_min_speed_cm_s'] and acceleration>=p['pivot_acceleration_cm_s2'] and
               pred_dot<=math.cos(math.radians(p['pivot_angle_degrees']))))
        pivot=pivot and not self.pivot_latched and self.pivot_cooldown<=0
        turn_delta=wrap(aim-self.visual_yaw)
        if self.last_missing_turn_aim is not None and abs(wrap(aim-self.last_missing_turn_aim))>p['turn_exit_degrees']:
            self.last_missing_turn_aim=None
        # Interruption priority: movement > turn, reversal > stop, restart > stop completion.
        if self.state=='turn':
            if moving or intent: self._enter('start',self.direction_name)
            elif self.action and abs(wrap(aim-self.action['aim_at_entry']))>p['turn_exit_degrees'] and abs(turn_delta)<=p['turn_exit_degrees']:
                self._enter('idle')
            elif self.action and turn_delta*self.table[self.action['asset_id']]['semantic']['anatomical_turn_degrees']>0 and abs(turn_delta)>p['turn_abort_opposite_degrees']:
                self._enter('idle')
            elif self.action and self.action['complete']:
                if self.table[self.action['asset_id']]['data'] is None: self.last_missing_turn_aim=aim
                self._enter('idle')
        if self.state=='idle':
            if moving or intent: self._enter('start',self.direction_name)
            elif abs(turn_delta)>=p['turn_enter_degrees'] and self.turn_cooldown<=0 and self.last_missing_turn_aim is None:
                self._enter('turn',aim=aim,turn_delta=turn_delta)
        elif self.state in ('start','cycle','stop','pivot'):
            if pivot and self.state!='pivot':
                self._enter('pivot',incoming,action_gait=incoming_gait); self.pivot_latched=True
            elif self.state=='start':
                if stopped and not intent and self.state_age>p['start_min_seconds']: self._enter('stop',self.action['direction'],action_gait=self.action['gait_at_entry'])
                elif (self.direction_name!=self.action['direction'] or self.gait!=self.action['gait_at_entry']) and self.state_age>p['start_min_seconds']:
                    self._enter('start',self.direction_name)
                elif self.action['complete'] or self.state_age>=p['start_timeout_seconds']:
                    self._enter('cycle' if not stopped else 'idle')
                elif braking and speed/max(decel,1.)<=p['stop_prediction_seconds'] and self.state_age>p['start_min_seconds']:
                    self._enter('stop',self.direction_name,action_gait=incoming_gait)
            elif self.state=='cycle':
                if stopped or (braking and speed/max(decel,1.)<=p['stop_prediction_seconds']): self._enter('stop',self.direction_name,action_gait=incoming_gait)
            elif self.state=='stop':
                if moving and (dot>p['intent_acceleration_cm_s2'] or not braking): self._enter('start',self.direction_name)
                elif self.action['complete']: self._enter('idle' if stopped else 'cycle')
            elif self.state=='pivot':
                if stopped and not intent and self.state_age>=p['pivot_min_hold_seconds']: self._enter('stop',self.action['direction'],action_gait=self.action['gait_at_entry'])
                elif self.action['complete']: self._enter('cycle' if not stopped else 'idle')
        # Gameplay owns actor yaw. Only mesh-relative visual facing is maintained here.
        if self.state not in ('idle','turn'):
            offset=wrap(self.visual_yaw-actor)*math.exp(-math.log(2)*dt/p['moving_facing_halflife_seconds'])
            self.visual_yaw=wrap(actor+offset)
        # Advance outgoing players; incoming players overwrite their authoritative clocks below.
        for player in self.players.values():
            data=self.table[player['asset_id']]['data']
            if data and player['sample_time_seconds'] is not None:
                t=player['sample_time_seconds']+dt*player['play_rate']; duration=data['duration_seconds']
                if player['loop']:
                    lo,hi=data.get('loop_range_seconds') or [0.,duration]
                    player['sample_time_seconds']=lo+(t-lo)%(hi-lo)
                else:
                    previous=player['sample_time_seconds']
                    player['sample_time_seconds']=min(t,duration)
                    player['play_rate']=(player['sample_time_seconds']-previous)/dt
        cycles=self._cycle_targets(speed,dt)
        if self.state=='cycle': targets=cycles
        elif self.state=='idle':
            aid=self.bindings['idle']; pid='idle'; data=self.table[aid]['data']
            self.players[pid]={'player_id':pid,'asset_id':aid,'sample_time_seconds':self.total_time%data['duration_seconds'] if data else None,
                               'play_rate':1. if data else 0.,'loop':True,'clock':'idle'}
            targets={pid:1.}
        else: targets=self._advance_action(speed,decel,dt)
        if not self.weights: self.weights=dict(targets)
        else:
            # Bounded first-order fade handles arbitrary interruptions without resurrecting time=0.
            for pid in sorted(set(self.weights)|set(targets)):
                self.weights[pid]=smooth(self.weights.get(pid,0.),targets.get(pid,0.),dt,p['blend_seconds']/3.)
            self.weights={pid:w for pid,w in self.weights.items() if w>1e-5}
        total=sum(self.weights.values()); players=[]
        for pid in sorted(self.weights):
            player=dict(self.players[pid]); player['weight']=self.weights[pid]/total
            asset=self.table[player['asset_id']]
            player['availability']=asset['status']; player['pose_materializable']=asset['status']=='ready'
            if not player['pose_materializable']: player['sample_time_seconds']=None
            players.append(player)
        self.players={pid:self.players[pid] for pid in self.weights}
        sync_members=[x['player_id'] for x in players if x['player_id'].startswith('cycle_')]
        leader=min((x for x in players if x['player_id'] in sync_members),key=lambda x:(-x['weight'],x['asset_id']),default=None)
        groups=[{'group_id':self.group_id,'member_player_ids':sync_members,
                 'settings':{'mode':self.group_config['mode'],'phase':self.phase,'leader_player_id':leader['player_id'] if leader else None,
                             'time_authority':'controller; never independently advance or reset followers','action_members':False,
                             'marker_mapping':{'L':0.,'R':.5,'next_L':1.},'fallback':self.group_config['fallback']}}]
        weights={x['player_id']:x['weight'] for x in players}
        ops=[{'operation_id':'blend','operation_type':'weighted_pose_blend','inputs':list(weights),
              'parameters':{'weights':weights,'rotation_interpolation':'shortest_arc_quaternion','missing_pose_policy':'unresolved; do not invent bind/idle pose'}}]
        def op(oid,kind,parameters):
            ops.append({'operation_id':oid,'operation_type':kind,'inputs':[ops[-1]['operation_id']],'parameters':parameters})
        offset=clamp(wrap(self.visual_yaw-actor),-p['turn_max_offset_degrees'],p['turn_max_offset_degrees'])
        op('facing','component_root_yaw_offset',{'yaw_degrees':offset,'rotate_all_component_transforms':True,'apply_gameplay_root_motion':False})
        warp=0.
        if self.action and self.state in ('start','stop','pivot'):
            reference=self.angles[self.action['direction']]
            warp=self.action['entry_warp_degrees'] if self.state=='pivot' else clamp(wrap(raw_direction-reference),-p['orientation_warp_limit_degrees'],p['orientation_warp_limit_degrees'])
        op('orientation','orientation_warp_intent',{'yaw_degrees':warp,'policy':'limited action alignment; cycles already directionally blended'})
        nominal=sum(x['weight']*(self.table[x['asset_id']]['data'] or {}).get('average_speed_cm_s',0.)*x['play_rate'] for x in players)
        stride=clamp(speed/max(nominal,1.),p['stride_scale_min'],p['stride_scale_max']) if self.state in ('start','cycle','pivot') else 1.
        op('stride','stride_warp_intent',{'scale':stride,'pelvis':self.nodes['stride']['pelvis'],'feet':self.nodes['stride']['feet'],'direction_actor_xy':[math.cos(math.radians(raw_direction)),math.sin(math.radians(raw_direction))]})
        self.lean=[smooth(self.lean[k],clamp(local_a[k]*p['lean_acceleration_scale'],-p['lean_max_degrees'],p['lean_max_degrees']),dt,p['lean_smoothing_seconds']) for k in range(2)]
        op('lean','acceleration_lean_intent',{'pitch_degrees':self.lean[0],'roll_degrees':-self.lean[1],'bones':self.nodes['lean']['bones'],'not_an_authored_additive_pose':True})
        contacts={}; coverage=0.
        for foot in self.nodes['feet']['feet']:
            value=0.
            for player in players:
                data=self.table[player['asset_id']]['data']
                if data and data.get('contact_estimates') and player['sample_time_seconds'] is not None:
                    curve=data['contact_estimates']['feet'][foot]['weights']
                    value+=player['weight']*interpolate(data['sample_times_seconds'],curve,player['sample_time_seconds'])
            contacts[foot]=value
        coverage=sum(x['weight'] for x in players if self.table[x['asset_id']]['data'] is not None)
        op('feet','foot_ik_intent',{'enabled':p['foot_ik_enabled'],'feet':self.nodes['feet']['feet'],'ground_model':'flat local plane; world lock unavailable without actor position', 'contact_weights':contacts,'sampled_weight_coverage':coverage,'unknown_contact_weight':max(0.,1.-coverage),'contact_source':'measured heuristic curves, not actual solver contacts','execution':'not evaluated; no solver supplied'})
        self.prev_velocity=v[:2]; self.prev_actor=actor
        missing=[x['asset_id'] for x in players if not x['pose_materializable']]
        return {'schema_version':1,'players':players,'sync_groups':groups,'pose_operations':ops,
                'diagnostics':{'state':self.state,'state_age_seconds':self.state_age,'gait':self.gait,'jog_weight':self.jog_alpha,
                    'speed_cm_s':speed,'direction_actor_degrees':raw_direction,'local_velocity_cm_s':local_v,
                    'local_acceleration_cm_s2':local_a,'aim_actor_delta_degrees':wrap(aim-actor),
                    'last_transition':self.last_transition,'deferred_asset_ids':sorted(set(missing)),
                    'all_referenced_samples_available':not missing,'output_kind':'execution_plan_not_evaluated_pose',
                    'ignored_vertical_inputs':True}}
