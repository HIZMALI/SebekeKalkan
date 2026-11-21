"""R1 fiziksel sayısal kapı: model kapsamıyla sınırlı, saha onayı değildir."""
from pathlib import Path
import numpy as np
import pandas as pd

def assess(model,frames,assignments=(),failure_start_hour=2):
    times=frames['head'].index.to_numpy(dtype=float);dt=np.diff(times)
    finite=all(np.isfinite(f.to_numpy()).all() for f in frames.values())
    time_ok=bool(len(times)>1 and times[0]==0 and times[-1]==model.options.time.duration and (dt>0).all())
    tanks={}
    for name,tank in model.tanks():
        levels=frames['head'][name].to_numpy()-tank.elevation
        if tank.vol_curve is None:volumes=(np.pi*tank.diameter**2/4)*levels
        else:volumes=np.interp(levels,*np.asarray(tank.vol_curve.points).T)
        net=np.zeros(len(times))
        for link,obj in model.links():
            if obj.start_node_name==name:net-=frames['flowrate'][link].to_numpy()
            if obj.end_node_name==name:net+=frames['flowrate'][link].to_numpy()
        residual=np.diff(volumes)-net[:-1]*dt;scale=float(np.sum(np.abs(net[:-1]*dt)))
        min_out=(levels<=tank.min_level+1e-6)&(net < -1e-6)
        tanks[name]={'bounds_pass':bool(levels.min()>=tank.min_level-.001 and levels.max()<=tank.max_level+.001),
                     'maximum_bound_violation_m':max(0,float(tank.min_level-levels.min()),float(levels.max()-tank.max_level)),
                     'min_outflow_pass':not bool(min_out.any()),'min_outflow_samples':int(min_out.sum()),
                     'mass_balance_pass':bool(np.sum(np.abs(residual)) <= .05+1e-5*scale),
                     'sum_abs_residual_m3':float(np.sum(np.abs(residual))),'allowed_residual_m3':.05+1e-5*scale,
                     'initial_level_matches':bool(abs(levels[0]-tank.init_level)<1e-6)}
    requested=pd.DataFrame({name:[j.demand_timeseries_list.at(t,multiplier=model.options.hydraulic.demand_multiplier) for t in times] for name,j in model.junctions()},index=times)
    pressure=frames['pressure'][requested.columns].to_numpy();wanted=requested.to_numpy();actual=frames['demand'][requested.columns].to_numpy()
    p0=model.options.hydraulic.minimum_pressure;p1=model.options.hydraulic.required_pressure;e=model.options.hydraulic.pressure_exponent
    theory=wanted*np.clip((pressure-p0)/(p1-p0),0,1)**e;mask=wanted>0
    pdd_ok=bool(np.allclose(actual[mask],theory[mask],rtol=1e-3,atol=2e-6))
    events=[]
    for assignment in assignments:
        name=assignment['pipe_id'];end=assignment['ends_at_h']*3600
        closed=(times>=failure_start_hour*3600)&(times<end)
        after=np.where(times>=end)[0]
        ok=bool((frames['status'].loc[closed,name]==0).all() and np.max(np.abs(frames['flowrate'].loc[closed,name].to_numpy()),initial=0)<1e-7 and len(after) and frames['status'][name].iloc[after[0]]!=0)
        events.append({'pipe':name,'pass':ok})
    passed=finite and time_ok and pdd_ok and all(all(t[k] for k in ['bounds_pass','min_outflow_pass','mass_balance_pass','initial_level_matches']) for t in tanks.values()) and all(e['pass'] for e in events)
    return {'pass':passed,'finite':finite,'full_horizon_and_monotonic_time':time_ok,'tanks':tanks,'pdd_pass':pdd_ok,'events':events,
            'negative_pressure_samples_preserved':int((pressure<-1e-6).sum()),
            'scope':'Bu model/olay koşusunda kütle, sınır ve PDD denklemleri; saha basıncı, vakum/kavitasyon veya bütün ağlar için doğruluk sertifikası değildir.'}

def read_frames(folder):return {name:pd.read_csv(Path(folder)/(name+'.csv'),index_col=0) for name in ['head','pressure','demand','flowrate','status']}
