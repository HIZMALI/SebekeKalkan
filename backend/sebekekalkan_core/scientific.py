"""Ön kayıtlı deney yürütücüsü; BUILD 01 fiziksel motorunu değiştirmez."""
from datetime import datetime,timezone
import argparse
import hashlib
import heapq
import itertools
import json
import platform
import time
import traceback
from importlib.metadata import distributions
from pathlib import Path

import numpy as np

from .contracts import Scenario
from .hydraulics import simulate
from .networks import ROOT,MODEL
from .planning import objective,oracle_schedule,schedule,write_json

OUT=ROOT/'experiments/results/build02'
PROTOCOL=ROOT/'experiments/configs/build02_s_protocol_v1.json'
METRICS=['weighted_unmet_volume_m3','critical_low_pressure_node_hours','repair_completion_hour']

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()

def registered():
    lock=json.loads((OUT/'registration/lock.json').read_text(encoding='utf-8'))
    for name,sha in lock['files'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Kilitli protokol/matris değişmiş: '+name)
    protocol=json.loads(PROTOCOL.read_text(encoding='utf-8'))
    if digest(MODEL)!=protocol['model_sha256']:raise ValueError('Sabit Net3 değişmiş.')
    inventory=json.loads((OUT/'inventory_before.json').read_text(encoding='utf-8'))
    frozen={}
    for name,sha in inventory['source']['backend'].items():
        if name.endswith(('hydraulics.py','planning.py','contracts.py','networks.py','sebeke.py')):
            if digest(ROOT/'backend'/name)!=sha:raise ValueError('BUILD 01 motoru değişmiş: '+name)
            frozen[name]=sha
    return protocol,lock,frozen

def close(a,b,rtol=1e-8,atol=1e-6):return abs(a-b)<=atol+rtol*max(abs(a),abs(b))
def lex_compare(a,b):
    """−1: a daha iyi, 0: toleransla eşit, +1: a daha kötü."""
    for x,y in zip(a,b):
        if not close(x,y):return -1 if x<y else 1
    return 0
def equal_objective(a,b):return all(close(x,y) for x,y in zip(a,b))

def software():
    return {'python':platform.python_version(),'platform':platform.platform(),
            'packages':{d.metadata['Name']:d.version for d in distributions()}}

def dispatch_with_access(scenario,order,delays):
    """Gerçekleşme deneyi: ekip erişim saatli bağımsız heap; motor değiştirilmez."""
    heap=[(scenario.failure_start_hour+delays[i],i+1) for i in range(scenario.crews)]
    heapq.heapify(heap);hours={f.pipe_id:f.repair_hours for f in scenario.failures};out=[]
    for pipe in order:
        starts,crew=heapq.heappop(heap);ends=starts+hours[pipe]
        out.append({'pipe_id':pipe,'crew':crew,'starts_at_h':starts,'ends_at_h':ends})
        heapq.heappush(heap,(ends,crew))
    return out

class Recorder:
    def __init__(self,folder,scenario):self.folder=folder;self.scenario=scenario;self.plans={}
    def run(self,key,assignments,solver='epanet'):
        path=self.folder/key;started=now()
        try:
            raw=simulate(self.scenario,assignments,path,solver=solver)
            write_json(path/'physical.json',raw)
            status={'status':'completed','started_utc':started,'finished_utc':now(),'assignments':assignments,
                    'metrics':raw['metrics'],'objective':list(objective(raw)),
                    'negative_pressure_samples':int((np.asarray(raw['pressure_m'])< -1e-6).sum()),
                    'negative_flow_samples':int((np.asarray(raw['flowrate_m3s'])< -1e-8).sum()),
                    'zero_base_demand_notice':'Ham bütün düğümler korunur; müşteri açığı yalnız pozitif istenen talepte.',
                    'warnings':raw['warnings'],'solver_warnings_original':raw['solver_warnings_original'],
                    'physical_json':str((path/'physical.json').relative_to(self.folder))}
        except Exception as error:
            path.mkdir(parents=True,exist_ok=True)
            status={'status':'failed','started_utc':started,'finished_utc':now(),'assignments':assignments,
                    'message':str(error),'exception':type(error).__name__,'cause':repr(error.__cause__),
                    'stage':key}
            (path/'exception.log').write_text(traceback.format_exc(),encoding='utf-8')
        write_json(path/'status.json',status)
        self.plans[key]=status
        write_json(self.folder/'progress.json',{'plans':self.plans,'updated_utc':now()})
        return status

def choose(plans):
    return min(plans,key=lambda p:(p['objective'],p['order']))

def compare_case(scenario,folder):
    recorder=Recorder(folder,scenario);ids=[f.pipe_id for f in scenario.failures]
    baseline=recorder.run('baseline',[])
    fifo=recorder.run('fifo',schedule(scenario,ids))
    scores={};single=[]
    for i,f in enumerate(scenario.failures):
        value=recorder.run(f'single-{i}',[{'pipe_id':f.pipe_id,'crew':1,'starts_at_h':scenario.failure_start_hour,'ends_at_h':scenario.horizon_hours}]);single.append(value)
        if value['status']=='completed' and baseline['status']=='completed':
            scores[f.pipe_id]=(value['metrics'][METRICS[0]]-baseline['metrics'][METRICS[0]])/f.repair_hours
    if len(scores)==len(ids):
        greedy_order=sorted(ids,key=lambda p:(-scores[p],p))
        greedy=recorder.run('greedy',schedule(scenario,greedy_order))
    else:
        greedy={'status':'not_computable','message':'Tekli fiziksel etki veya baz başarısız; sezgisel sıra tanımlanmadı.'}
    candidates=[];oracle=[]
    for i,order in enumerate(itertools.permutations(ids)):
        record=recorder.run(f'search-{i}',schedule(scenario,order))
        candidates.append({'order':list(order),'plan':f'search-{i}',**record})
    for i,order in enumerate(itertools.permutations(sorted(ids))):
        record=recorder.run(f'oracle-{i}',oracle_schedule(scenario,order))
        oracle.append({'order':list(order),'plan':f'oracle-{i}',**record})
    all_search=all(p['status']=='completed' for p in candidates)
    all_oracle=all(p['status']=='completed' for p in oracle)
    best=choose(candidates) if all_search else None
    ref=choose(oracle) if all_oracle else None
    oracle_ok=False;ties=[]
    if best and ref:
        byorder={tuple(p['order']):p for p in oracle}
        oracle_ok=equal_objective(best['objective'],ref['objective']) and all(equal_objective(p['objective'],byorder[tuple(p['order'])]['objective']) for p in candidates)
    if best and oracle_ok:
        ties=[p['order'] for p in candidates if equal_objective(p['objective'],best['objective'])]
        proposal=recorder.run('proposal',schedule(scenario,best['order']))
    else:
        proposal={'status':'not_verified','message':'Altı aday ve bağımsız referansın tamamı doğrulanamadı; optimum öneri sunulmadı.'}
    manual=recorder.run('manual',schedule(scenario,scenario.manual_order)) if scenario.manual_order else {'status':'not_requested'}
    methods={'fifo':fifo,'greedy':greedy,'proposal':proposal,'manual':manual}
    complete=baseline['status']=='completed' and all(p['status']=='completed' for p in methods.values()) and oracle_ok
    return {'status':'completed' if complete else 'partial_or_failed','baseline':baseline,'methods':methods,
            'search':{'candidates':candidates,'oracle':oracle,'all_candidates_completed':all_search,
                      'oracle_verified':oracle_ok,'chosen_order':best['order'] if best and oracle_ok else None,
                      'optimal_ties':len(ties),'optimal_orders':ties,'greedy_scores':scores},
            'plans':recorder.plans}

def uncertainty_case(scenario,folder,case_id,protocol):
    nominal=json.loads((OUT/'main'/case_id/'result.json').read_text(encoding='utf-8'))
    if nominal['status']!='completed':return {'status':'not_computable','message':'Nominal vaka tam değil; yeni vaka seçilmedi.'}
    priorities={key:[a['pipe_id'] for a in plan['assignments']] for key,plan in nominal['methods'].items()}
    realizations=[]
    for perturbation in protocol['uncertainty']['realizations']:
        config=scenario.model_dump()
        for f,delta in zip(config['failures'],perturbation['repair_delta_h']):f['repair_hours']+=delta
        realized=Scenario.model_validate(config)
        at=folder/perturbation['id'];at.mkdir();write_json(at/'input.json',realized.model_dump())
        recorder=Recorder(at,realized);delays=perturbation['crew_delay_h']
        base=recorder.run('baseline',[])
        methods={key:recorder.run('nominal-'+key,dispatch_with_access(realized,order,delays)) for key,order in priorities.items()}
        oracle=[]
        for i,order in enumerate(itertools.permutations(sorted(priorities['fifo']))):
            plan=recorder.run(f'oracle-{i}',dispatch_with_access(realized,order,delays))
            oracle.append({'order':list(order),**plan})
        best=choose(oracle) if all(p['status']=='completed' for p in oracle) else None
        result={'id':perturbation['id'],'parameters':perturbation,'scenario':realized.model_dump(),
                'baseline':base,'methods':methods,'oracle':oracle,'best':best,
                'status':'completed' if best and base['status']=='completed' and all(p['status']=='completed' for p in methods.values()) else 'partial_or_failed'}
        if best:
            result['optimal_orders']=[p['order'] for p in oracle if equal_objective(p['objective'],best['objective'])]
            result['nominal_order_stable']={key:any(order==o for o in result['optimal_orders']) for key,order in priorities.items()}
        write_json(at/'result.json',result);realizations.append(result)
    return {'status':'completed' if all(r['status']=='completed' for r in realizations) else 'partial_or_failed',
            'nominal_priorities':priorities,'realizations':realizations,'new_robust_optimizer':False}

def run(mode,case_id,step,folder):
    protocol,lock,frozen=registered()
    if mode=='anchor':
        scenario=Scenario.model_validate_json((ROOT/'experiments/configs/example.json').read_text(encoding='utf-8'))
        scenario.manual_order=list(reversed([f.pipe_id for f in scenario.failures]))
        descriptor={'case_id':'BUILD01_anchor','cluster_id':'excluded_anchor','stratum':'prior_known'}
    else:
        descriptor=next(c for c in protocol['cases'] if c['case_id']==case_id)
        config=dict(descriptor['scenario'])
        if step:
            if case_id not in protocol['sensitivity']['case_ids'] or step not in protocol['sensitivity']['alternatives_minutes']:
                raise ValueError('Ön kayıt dışı duyarlılık koşusu.')
            config['step_minutes']=step
        scenario=Scenario.model_validate(config)
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'result.json').exists():raise ValueError('Tamamlanmış deney üzerine yazılmadı.')
    write_json(folder/'input.json',scenario.model_dump())
    started=now();timer=time.perf_counter()
    if mode in ('main','sensitivity','anchor'):result=compare_case(scenario,folder)
    elif mode=='uncertainty':result=uncertainty_case(scenario,folder,case_id,protocol)
    elif mode=='cross':
        recorder=Recorder(folder,scenario);assign=schedule(scenario,[f.pipe_id for f in scenario.failures])
        epanet=recorder.run('epanet',assign);wntr=recorder.run('wntr',assign,solver='wntr')
        result={'status':'completed' if epanet['status']==wntr['status']=='completed' else 'partial_or_failed','epanet':epanet,'wntr':wntr}
        if result['status']=='completed':
            a=json.loads((folder/'epanet/physical.json').read_text(encoding='utf-8'));b=json.loads((folder/'wntr/physical.json').read_text(encoding='utf-8'))
            differences={}
            for key,index in [('pressure_m','node_ids'),('head_m','node_ids'),('demand_m3s','node_ids'),('flowrate_m3s','link_ids')]:
                order=[b[index].index(n) for n in a[index]]
                differences[key]=float(np.max(np.abs(np.asarray(a[key])-np.asarray(b[key])[:,order])))
            result['max_abs_differences']=differences
    else:raise ValueError('Bilinmeyen deney türü.')
    result.update(case_id=descriptor['case_id'],cluster_id=descriptor['cluster_id'],stratum=descriptor['stratum'],mode=mode,
                  input=scenario.model_dump(),input_sha256=digest(folder/'input.json'),model_sha256=digest(MODEL),
                  protocol_sha256=digest(PROTOCOL),registration=lock,engine_hashes=frozen,
                  started_utc=started,finished_utc=now(),total_seconds=time.perf_counter()-timer,software=software(),
                  leakage_volume_m3=None,metric_notice='V_w: ağırlıklandırılmış hizmet açığı; V: karşılanamayan müşteri talebi. Kaçak su değil.')
    write_json(folder/'result.json',result)
    write_json(folder/'output-hashes.json',{p.relative_to(folder).as_posix():digest(p) for p in folder.rglob('*') if p.is_file() and p.name not in ('worker.log','output-hashes.json')})
    print(json.dumps({'mode':mode,'case':case_id,'step':step,'status':result['status'],'seconds':result['total_seconds']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Ön kayıtlı ŞebekeKalkan bilimsel deney koşusu')
    parser.add_argument('--mode',choices=['main','sensitivity','uncertainty','anchor','cross'],required=True)
    parser.add_argument('--case',default='T01_C1');parser.add_argument('--step',type=int);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=args.output.resolve()
    if not target.is_relative_to(ROOT):raise SystemExit('Çıktı yolu proje içinde olmalı.')
    run(args.mode,args.case,args.step,target)
