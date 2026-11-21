"""Budgeted restoration search on four *given* failures. No oracle or external I/O."""
from itertools import combinations, permutations
import math

import networkx as nx

from .planning import schedule
from .s02_physics import METRICS, close


def signature(assignments):
    """Hydraulic identity: all four close together; crew labels do not enter the solver."""
    return tuple(sorted((a["pipe_id"], a["ends_at_h"]) for a in assignments))


def greedy_order(scenario, baseline, singles):
    scores = {f.pipe_id: (singles[f.pipe_id] - baseline) / f.repair_hours for f in scenario.failures}
    return tuple(sorted(scores, key=lambda name: (-scores[name], name))), scores


def lost_on_disconnection(model, unavailable, initially_open, sources, weighted_demand):
    graph = nx.Graph()
    graph.add_nodes_from(model.node_name_list)
    graph.add_edges_from((link.start_node_name, link.end_node_name) for name,link in model.links()
                         if name in initially_open and name not in unavailable)
    return sum(weighted_demand.get(node,0) for island in nx.connected_components(graph)
               if island.isdisjoint(sources) for node in island)


def rank_schedules(scenario, model, fifo, single_rates, initially_open, sources, weighted_demand):
    """Only cheap surrogate scores for permutations; no hydraulic simulations here."""
    n = len(fifo)
    rates = {}
    for size in range(1, n+1):
        for subset in combinations(fifo,size):
            missing = frozenset(subset)
            isolated = lost_on_disconnection(model,missing,initially_open,sources,weighted_demand)
            rates[missing] = max(isolated,sum(single_rates[p] for p in missing))
    ranked=[]
    for order in permutations(fifo):
        assignment=schedule(scenario,order)
        by_pipe=dict(signature(assignment))
        previous=scenario.failure_start_hour
        area=0.0
        for end in sorted(set(by_pipe.values())):
            pending=frozenset(p for p,when in by_pipe.items() if when>previous)
            area+=rates[pending]*(end-previous)*3600
            previous=end
        ranked.append((area,previous,order,signature(assignment)))
    return sorted(ranked)


def candidates(ranked, fifo, greedy, budget):
    if budget not in (6,12) or len(ranked)!=24:
        raise ValueError("Dört arıza ve ön kayıtlı 6/12 bütçesi gerekli.")
    fifo,greedy=tuple(fifo),tuple(greedy)
    by_order={x[2]:x for x in ranked}
    if set(by_order)!=set(permutations(fifo)) or greedy not in by_order:
        raise ValueError("Başlangıçlar aynı dört arızayı içermeli.")
    neighbours=set()
    for seed in (fifo,greedy):
        for i,j in combinations(range(4),2):
            p=list(seed);p[i],p[j]=p[j],p[i];neighbours.add(tuple(p))
    queues=[iter(ranked),iter([x for x in ranked if x[2] in neighbours])]
    chosen=[];seen=set()
    def admit(row):
        if row[3] not in seen:
            chosen.append(row[2]);seen.add(row[3])
            return True
        return False
    for seed in (fifo,greedy):
        admit(by_order[seed])
    goal=min(budget,len({x[3] for x in ranked}))
    while len(chosen)<goal:
        advanced=False
        for queue in queues:
            for row in queue:
                if admit(row):
                    advanced=True
                    break
            if len(chosen)==goal:break
        if not advanced:raise RuntimeError("Beklenen benzersiz çizelgeler tüketilemedi.")
    return chosen


def select_verified(pool):
    if not pool or any(c.get("status")!="PASS" for c in pool):
        raise ValueError("Eksik veya doğrulanmamış aday havuzu.")
    if any(not math.isfinite(c["metrics"][m]) for c in pool for m in METRICS):
        raise ValueError("Sonlu olmayan ölçüm.")
    remaining=list(pool)
    for metric in ("weighted_unmet_volume_m3","critical_low_pressure_node_hours"):
        minimum=min(c["metrics"][metric] for c in remaining)
        remaining=[c for c in remaining if close(c["metrics"][metric],minimum)]
    finish=min(c["metrics"]["repair_completion_hour"] for c in remaining)
    return min((c for c in remaining if c["metrics"]["repair_completion_hour"]==finish),key=lambda c:c["order"])
