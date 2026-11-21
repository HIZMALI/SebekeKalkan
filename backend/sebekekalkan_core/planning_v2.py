"""Sürüm 2: aynı aday havuzu, WNTR fizik kapısı ve bağımsız taze oracle."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,itertools,json,platform,time,traceback
from pathlib import Path
import numpy as np
from .decision_policy_v2 import select,evaluate_methods
from .hydraulics_v2 import simulate_checked
from .planning import schedule,oracle_schedule,objective,write_json,export_csv
from .networks import AnalysisError,MANIFEST

VERSION='SK-WNTR-v2.0'
IMPLEMENTATION_REVISION='oracle-tolerance-r2'

def reference_matches(decision,reference):
    return decision['selected']['order']==reference['selected']['order'] and bool(np.allclose(decision['selected']['objective'],reference['selected']['objective'],rtol=1e-8,atol=1e-6))

def compare_v2(scenario,destination:Path):
    started=time.perf_counter();destination.mkdir(parents=True,exist_ok=True)
    if (destination/'result.json').exists():raise AnalysisError('Tamamlanmış deneyin üzerine yazılmaz; yeni çıktı yolu seçin.')
    write_json(destination/'input.json',scenario.model_dump());runs=[]
    def run(key,assigned):
        try:
            value=simulate_checked(scenario,assigned,destination/key)
            runs.append({'key':key,'status':'completed','objective':list(objective(value)),'physical_gate':True})
            write_json(destination/'progress.json',{'plans':runs})
            return value
        except Exception as error:
            runs.append({'key':key,'status':'failed','message':str(error),'cause':repr(error.__cause__)})
            write_json(destination/'progress.json',{'plans':runs});raise
    try:
        baseline=run('baseline',[]);ids=[f.pipe_id for f in scenario.failures];scores={}
        for i,f in enumerate(scenario.failures):
            value=run(f'single-{i}',[{'pipe_id':f.pipe_id,'crew':1,'starts_at_h':scenario.failure_start_hour,'ends_at_h':scenario.horizon_hours}])
            scores[f.pipe_id]=(value['metrics']['weighted_unmet_volume_m3']-baseline['metrics']['weighted_unmet_volume_m3'])/f.repair_hours
        candidates=[];physical={}
        for i,order in enumerate(itertools.permutations(ids)):
            assigned=schedule(scenario,order);value=run(f'candidate-{i}',assigned);physical[tuple(order)]=value
            candidates.append({'order':list(order),'objective':list(objective(value)),'status':'completed'})
        decision=select(candidates);oracles=[]
        for i,order in enumerate(itertools.permutations(sorted(ids))):
            independent=oracle_schedule(scenario,order);value=run(f'oracle-{i}',independent)
            if independent!=schedule(scenario,order) or not np.allclose(objective(value),objective(physical[tuple(order)]),rtol=1e-8,atol=1e-6):
                raise AnalysisError('Bağımsız ekip çizelgesi/hidrolik hedefi uyuşmadı; optimum sunulmadı.')
            oracles.append({'order':list(order),'objective':list(objective(value)),'status':'completed'})
        reference=select(oracles)
        if not reference_matches(decision,reference):raise AnalysisError('Bağımsız v2 sıra seçimi uyuşmadı.')
        orders={'fifo':ids,'greedy':sorted(ids,key=lambda p:(-scores[p],p)),'proposal':decision['selected']['order']}
        if scenario.manual_order:orders['manual']=scenario.manual_order
        assessed=evaluate_methods(candidates,orders);names={'fifo':'Bildirim sırası','greedy':'Tekli etki / onarım süresi','proposal':'ŞebekeKalkan önerisi','manual':'Elle belirlenen sıra'}
        methods={}
        for key,order in orders.items():
            methods[key]=deepcopy(physical[tuple(order)]);methods[key]['name']=names[key]
            methods[key]['decision_classification']=assessed['methods'][key]
        result={'model_version':VERSION,'implementation_revision':IMPLEMENTATION_REVISION,
            'implementation_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*v2.py')},
            'decision_policy':'decision_policy_v2','solver':'WNTRSimulator 1.5.0',
            'input':scenario.model_dump(),'baseline':baseline,'methods':methods,'decision':decision,
            'search':{'candidate_count':len(candidates),'candidates':candidates,'oracle':oracles,'oracle_verified':True,
                      'optimal_ties':len(decision['equivalent_best_orders']),'optimal_orders':decision['equivalent_best_orders'],
                      'greedy_single_fault_score':scores,'scope':'Yalnız 1–3 boru ve 1–3 ekip için iş bekletmeyen öncelik sıraları. Genel sürekli zaman optimumu değildir.'},
            'physical_validation':{'pass':True,'plans_checked':len(runs),'scope':'Bütün baz/tekli/aday/oracle koşularında iç olay tank, kütle, PDD ve onarım kapısı.'},
            'unmet_reduction_vs_fifo_m3':methods['fifo']['metrics']['unmet_demand_volume_m3']-methods['proposal']['metrics']['unmet_demand_volume_m3'],
            'total_seconds':time.perf_counter()-started,'source_manifest':json.loads(MANIFEST.read_text(encoding='utf-8')),
            'created_utc':datetime.now(timezone.utc).isoformat(),'software':{'python':platform.python_version(),'wntr':'1.5.0'},
            'input_sha256':hashlib.sha256((destination/'input.json').read_bytes()).hexdigest(),'failure_type':'pipe_isolation_then_reopening','leakage_volume_m3':None,
            'integration':'Kayıtlı rapor ızgarasında sol dikdörtgen; son örnek süre taşımaz. Fizik kapısı ayrıca bütün iç olayları kullanır.',
            'explanation':'Her sıra taze WNTR modeliyle çözülür. Fizik kapısını geçen tam havuzda minimuma bağlı tolerans kümeleri, kritik süre, tam erken bitiş ve sabit boru kimliği bağı uygulanır. Sezgisel de aynı karar havuzuyla değerlendirilir.',
            'legacy_note':'Eski v1/EPANET sonuçları ve NO-GO-BILIMSEL korunur. Bu ürün sürümü ölçülmüş saha/kaçak kazanımı veya algoritmik üstünlük iddiası değildir.'}
        write_json(destination/'result.json',result);export_csv(result,destination/'summary.csv')
        write_json(destination/'output-hashes.json',{p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file() and p.name not in ['output-hashes.json','worker.log']})
        return result
    except Exception as error:
        write_json(destination/'failure.json',{'status':'failed','message':str(error),'cause':repr(error.__cause__),'exception':type(error).__name__,'plans':runs,'input':scenario.model_dump()})
        (destination/'exception.log').write_text(traceback.format_exc(),encoding='utf-8');raise
