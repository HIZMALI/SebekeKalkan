"""Bounded permutation search and an independently scheduled small oracle."""
import csv
import hashlib
import heapq
import itertools
import json
import platform
import sys
import time
from importlib.metadata import distributions
from pathlib import Path

import numpy as np

from .contracts import Scenario
from .hydraulics import simulate
from .networks import MANIFEST, AnalysisError
from .sebeke import RepairTask, allocate_crews


def schedule(scenario, order):
    hours = {f.pipe_id: f.repair_hours for f in scenario.failures}
    return [{'pipe_id': a.pipe_id, 'crew': a.crew + 1,
             'starts_at_h': a.starts_at_h + scenario.failure_start_hour,
             'ends_at_h': a.ends_at_h + scenario.failure_start_hour}
            for a in allocate_crews([RepairTask(p, hours[p]) for p in order], scenario.crews)]


def oracle_schedule(scenario, order):
    """Independent heap-based implementation; does not call the product scheduler."""
    available = [(float(scenario.failure_start_hour), c + 1) for c in range(scenario.crews)]
    heapq.heapify(available)
    duration = {f.pipe_id: f.repair_hours for f in scenario.failures}
    result = []
    for pipe in order:
        at, crew = heapq.heappop(available)
        finish = at + duration[pipe]
        result.append({'pipe_id': pipe, 'crew': crew, 'starts_at_h': at, 'ends_at_h': finish})
        heapq.heappush(available, (finish, crew))
    return result


def objective(result):
    metrics = result['metrics']
    return (metrics['weighted_unmet_volume_m3'], metrics['critical_low_pressure_node_hours'], metrics['repair_completion_hour'])


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def compare(scenario: Scenario, destination: Path):
    started = time.perf_counter()
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / 'input.json', scenario.model_dump())
    try:
        baseline = simulate(scenario, [], destination / 'baseline')
        ids = [f.pipe_id for f in scenario.failures]
        fifo = simulate(scenario, schedule(scenario, ids), destination / 'fifo')
        scores = {}
        for i, failure in enumerate(scenario.failures):
            # Single-fault severity with the pipe kept isolated until the common horizon.
            assessment = [{'pipe_id': failure.pipe_id, 'crew': 1,
                           'starts_at_h': scenario.failure_start_hour,
                           'ends_at_h': scenario.horizon_hours}]
            value = simulate(scenario, assessment, destination / f'single-{i}')
            scores[failure.pipe_id] = (value['metrics']['weighted_unmet_volume_m3'] - baseline['metrics']['weighted_unmet_volume_m3']) / failure.repair_hours
        greedy_order = sorted(ids, key=lambda p: (-scores[p], p))
        greedy = simulate(scenario, schedule(scenario, greedy_order), destination / 'greedy')
        candidates = []
        for i, order in enumerate(itertools.permutations(ids)):
            value = simulate(scenario, schedule(scenario, order), destination / f'search-{i}')
            candidates.append({'order': list(order), 'objective': objective(value)})
        chosen = min(candidates, key=lambda c: (c['objective'], c['order']))
        proposal = simulate(scenario, schedule(scenario, chosen['order']), destination / 'proposal')
        # Re-run every feasible order in fresh models using a separate crew implementation.
        oracle = []
        for i, order in enumerate(itertools.permutations(sorted(ids))):
            value = simulate(scenario, oracle_schedule(scenario, order), destination / f'oracle-{i}')
            oracle.append({'order': list(order), 'objective': objective(value)})
        reference = min(oracle, key=lambda c: (c['objective'], c['order']))
        verified = bool(np.allclose(chosen['objective'], reference['objective'], rtol=1e-8, atol=1e-6))
        if not verified:
            raise AnalysisError('Bağımsız sıra referansı önerilen planla uyuşmadı; optimumluk doğrulanamadı.')
        methods = {'fifo': fifo, 'greedy': greedy, 'proposal': proposal}
        if scenario.manual_order is not None:
            methods['manual'] = simulate(scenario, schedule(scenario, scenario.manual_order), destination / 'manual')
        names = {'fifo': 'Bildirim sırası', 'greedy': 'Tekli etki / onarım süresi', 'proposal': 'ŞebekeKalkan önerisi', 'manual': 'Elle belirlenen sıra'}
        for key, value in methods.items():
            value['name'] = names[key]
        delta = fifo['metrics']['unmet_demand_volume_m3'] - proposal['metrics']['unmet_demand_volume_m3']
        result = {
            'input': scenario.model_dump(), 'baseline': baseline, 'methods': methods,
            'search': {'candidate_count': len(candidates), 'candidates': candidates,
                       'oracle': oracle, 'oracle_verified': verified,
                       'optimal_ties': sum(np.allclose(c['objective'], chosen['objective'], rtol=1e-8, atol=1e-6) for c in candidates),
                       'scope': 'En fazla üç eşzamanlı izolasyon için iş bekletmeyen öncelik sıraları; küresel sürekli-zaman optimumu iddiası yok.',
                       'greedy_single_fault_score': scores},
            'unmet_reduction_vs_fifo_m3': delta,
            'total_seconds': time.perf_counter() - started,
            'source_manifest': json.loads(MANIFEST.read_text(encoding='utf-8')),
            'software': {'python': sys.version, 'platform': platform.platform(),
                         'packages': {d.metadata['Name']: d.version for d in distributions()}},
            'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'failure_type': 'pipe_isolation_then_reopening', 'leakage_volume_m3': None,
            'integration': 'Sol dikdörtgen: toplam max(istenen_i(t)-karşılanan_i(t),0)*Δt; yalnız pozitif müşteri talepleri, son örnek süre taşımaz.',
            'pdd': 'p≤0: 0; 0<p<gerekli basınç: D_istenen*(p/gerekli basınç)^0.5; yeterli basınçta tam talep.',
            'explanation': 'Öneri, aynı fiziksel koşullarda bütün küçük öncelik sıralarını hidrolik çözücüyle dener. Açgözlü yöntem, diğer arızaları hesaba katmayan tekli ek hidrolik etki/süre puanını kullanır; arızasız baz hacim puandan çıkarılır.',
        }
        result['input_sha256'] = hashlib.sha256((destination / 'input.json').read_bytes()).hexdigest()
        result['reproduce'] = 'python -m sebekekalkan_core.experiment --config ' + (destination / 'input.json').as_posix()
        write_json(destination / 'result.json', result)
        export_csv(result, destination / 'summary.csv')
        write_json(destination / 'output-hashes.json', {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file() and p.name not in ('worker.log', 'output-hashes.json')})
        return result
    except Exception as error:
        write_json(destination / 'failure.json', {'status': 'sonuç üretilemedi', 'message': str(error),
                   'exception': type(error).__name__, 'cause': repr(error.__cause__), 'input': scenario.model_dump(),
                   'elapsed_seconds': time.perf_counter() - started})
        raise


def export_csv(result, path):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['Yöntem', 'Zaman (s)', 'En düşük bağlantı basıncı (m)', 'İstenen müşteri talebi (m³/s)',
                         'Karşılanan müşteri talebi (m³/s)', 'Karşılanamayan talep (m³/s)', 'Toplam karşılanamayan hacim (m³)',
                         'Kritik düğüm düşük basınç süresi (düğüm·saat)', 'Girdi SHA-256', 'Model SHA-256', 'Üretim zamanı (UTC)'])
        for method in result['methods'].values():
            for i, at in enumerate(method['times_seconds']):
                writer.writerow([method['name'], at, method['minimum_junction_pressure_m'][i],
                                 method['expected_customer_demand_m3s'][i], method['delivered_customer_demand_m3s'][i],
                                 method['unmet_demand_m3s'][i], method['metrics']['unmet_demand_volume_m3'],
                                 method['metrics']['critical_low_pressure_node_hours'], result['input_sha256'], result['source_manifest']['sha256'], result['created_utc']])
