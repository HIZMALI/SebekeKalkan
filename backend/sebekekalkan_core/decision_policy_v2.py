"""Küresel minimuma sabitlenmiş tolerans kümeleri; v1'e dokunmaz."""
import hashlib
import json
import math

POLICY='decision_policy_v2'
ATOL=1e-6
RTOL=1e-8

class DecisionPolicyError(ValueError):pass

def select(candidates):
    if not candidates:raise DecisionPolicyError('Seçim için eksiksiz aday havuzu gerekli.')
    normalized=[];seen=set()
    for item in candidates:
        if item.get('status')!='completed':raise DecisionPolicyError('Başarısız/eksik hidrolik aday varken optimum seçim yapılamaz.')
        order=tuple(item.get('order',()))
        if not 1<=len(order)<=3 or any(not isinstance(p,str) or not p for p in order) or len(set(order))!=len(order):raise DecisionPolicyError('Adayın boru sırası geçersiz.')
        if order in seen:raise DecisionPolicyError('Aynı aday iki kez verilmiş.')
        seen.add(order);values=item.get('objective',())
        if not isinstance(values,(list,tuple)) or len(values)!=3 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values):
            raise DecisionPolicyError('Hedefin üç bileşeni sonlu sayı olmalı; NaN/inf kabul edilmez.')
        normalized.append({'order':list(order),'objective':[float(x) for x in values],'status':'completed'})
    universe=sorted(normalized,key=lambda c:c['order'])
    if any(set(c['order'])!=set(universe[0]['order']) for c in universe):raise DecisionPolicyError('Adaylar aynı boruları kapsamalı.')
    if len(universe)!=math.factorial(len(universe[0]['order'])):raise DecisionPolicyError('Bütün öncelik sıraları tamamlanmadan seçim yapılmaz.')
    pool=universe;stages=[]
    for component in (0,1):
        minimum=min(c['objective'][component] for c in pool)
        pool=[c for c in pool if abs(c['objective'][component]-minimum)<=ATOL+RTOL*max(abs(c['objective'][component]),abs(minimum))]
        stages.append({'component':component,'global_minimum_in_incoming_pool':minimum,'retained_orders':[c['order'] for c in pool]})
    finish=min(c['objective'][2] for c in pool)
    pool=[c for c in pool if c['objective'][2]==finish]
    stages.append({'component':2,'exact_minimum':finish,'retained_orders':[c['order'] for c in pool]})
    chosen=min(pool,key=lambda c:c['order'])
    payload={'policy':POLICY,'atol':ATOL,'rtol':RTOL,'candidates':universe,'stages':stages,
             'selected':chosen,'equivalent_best_orders':[c['order'] for c in pool],
             'legacy_raw_minimum':min(universe,key=lambda c:(c['objective'],c['order']))}
    canonical=json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)
    payload['decision_sha256']=hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return payload

def evaluate_methods(candidates,method_orders):
    """Bütün yöntemler tek ve aynı küresel aday kümesine göre sınıflanır."""
    decision=select(candidates)
    stages=[set(map(tuple,s['retained_orders'])) for s in decision['stages']]
    rows={}
    for name,order in method_orders.items():
        key=tuple(order)
        if key not in {tuple(c['order']) for c in decision['candidates']}:raise DecisionPolicyError('Yöntem sırası aday havuzunda yok.')
        rows[name]={'policy':POLICY,'decision_sha256':decision['decision_sha256'],
                    'in_best_set':key in stages[2],'first_rejected_component':next((i for i,s in enumerate(stages) if key not in s),None)}
    return {'decision':decision,'methods':rows}
