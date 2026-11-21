"""WNTR sonuçları, iç olay korunum kapısı geçmeden ürüne sunulmaz."""
from pathlib import Path
import time, warnings
import numpy as np
import wntr
from .hydraulics import model_for, simulate
from .numerical_gates_r1 import assess
from .networks import AnalysisError
from .planning import write_json

def simulate_checked(scenario, assignments, folder: Path):
    started=time.perf_counter()
    value=simulate(scenario,assignments,folder,solver='wntr')
    model=model_for(scenario,assignments)
    model.options.time.report_timestep='ALL'
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            raw=wntr.sim.WNTRSimulator(model).run_sim(solver_options={'MAXITER':getattr(scenario,'wntr_max_iterations',3000),'TIME_LIMIT':60},convergence_error=True)
        frames={n:getattr(raw,k)[f] for n,k,f in [('head','node','head'),('pressure','node','pressure'),('demand','node','demand'),('flowrate','link','flowrate'),('status','link','status')]}
        dense=folder/'internal_events';dense.mkdir()
        for name,frame in frames.items():frame.to_csv(dense/(name+'.csv'),encoding='utf-8-sig',index_label='zaman_saniye')
        gate=assess(model,frames,assignments,scenario.failure_start_hour)
        delta=float(np.max(np.abs(frames['pressure'].loc[value['times_seconds'],value['node_ids']].to_numpy()-np.asarray(value['pressure_m']))))
        gate.update(converged=not bool(raw.error_code),coarse_dense_pressure_delta_m=delta,
                    maxiter=getattr(scenario,'wntr_max_iterations',3000),solver_warnings_original=[str(w.message) for w in caught])
        gate['pass']=gate['pass'] and gate['converged'] and delta<1e-8
        write_json(folder/'physical-gate.json',gate)
        if not gate['pass']:raise AnalysisError('WNTR fiziksel doğrulama kapısı geçmedi. Depo/kütle/PDD/onarım kayıtları deney dosyasında; geçerli plan sunulmadı.')
    except AnalysisError:raise
    except Exception as error:
        raise AnalysisError('WNTR iç olay çözümü tamamlanamadı; yakınsama sınırını ve deney kaydını kontrol edin.') from error
    value['physical_gate']=gate;value['solver']='WNTRSimulator 1.5.0';value['model_version']='SK-WNTR-v2.0'
    value['metrics']['solver_seconds']=time.perf_counter()-started
    write_json(folder/'physical.json',value)
    return value
