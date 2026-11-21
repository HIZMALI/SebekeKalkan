"""Real EPANET 2.2 PDD results; signed flows/negative pressures remain visible."""
import time
import warnings
from pathlib import Path

import numpy as np
import wntr
from wntr.network.controls import Control, ControlAction, SimTimeCondition

from .contracts import Scenario
from .networks import AnalysisError, eligible_pipes, load_model


def validate_network(scenario, model):
    eligible = eligible_pipes(model)
    for failure in scenario.failures:
        if failure.pipe_id not in model.pipe_name_list:
            raise AnalysisError(f'{failure.pipe_id}: ağda böyle bir boru yok. Ağ listesinden seçim yapın.')
        if failure.pipe_id not in eligible:
            raise AnalysisError(f'{failure.pipe_id}: özgün kontrol/çekvalf nedeniyle bu sürümde izolasyona açık değil.')
    if set(scenario.critical_weights) - set(model.junction_name_list):
        raise AnalysisError('Kritik düğümler, doğrulanmış ağın bağlantı düğümlerinden seçilmeli.')


def model_for(scenario: Scenario, assignments):
    model = load_model()  # Always a new model, with all source initial physical states.
    validate_network(scenario, model)
    model.options.hydraulic.demand_model = 'PDD'
    model.options.hydraulic.minimum_pressure = 0
    model.options.hydraulic.required_pressure = scenario.required_pressure_m
    model.options.hydraulic.pressure_exponent = .5
    model.options.hydraulic.trials = scenario.hydraulic_trials
    model.options.hydraulic.unbalanced = 'STOP'
    model.options.time.duration = scenario.horizon_hours * 3600
    model.options.time.hydraulic_timestep = scenario.step_minutes * 60
    model.options.time.report_timestep = scenario.step_minutes * 60
    for i, assignment in enumerate(assignments):
        pipe = model.get_link(assignment['pipe_id'])
        for suffix, at, status in [('kapat', scenario.failure_start_hour * 3600, wntr.network.LinkStatus.Closed),
                                   ('ac', assignment['ends_at_h'] * 3600, wntr.network.LinkStatus.Open)]:
            control = Control(SimTimeCondition(model, '=', round(at)), ControlAction(pipe, 'status', status), priority=6)
            model.add_control(f'BUILD01_{i}_{suffix}', control)
    return model


def integrate(samples, seconds):
    """Left-rectangle integral: sample at t applies to [t,t+dt); terminal sample has no duration."""
    return float(np.dot(np.asarray(samples)[:-1], np.diff(np.asarray(seconds))))


def simulate(scenario: Scenario, assignments, folder: Path, solver='epanet'):
    if solver not in ('epanet', 'wntr'):
        raise AnalysisError('Desteklenmeyen hidrolik çözücü; EPANET veya WNTR seçin.')
    model = model_for(scenario, assignments)
    expected = wntr.metrics.expected_demand(model)
    folder.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            if solver == 'epanet':
                raw = wntr.sim.EpanetSimulator(model).run_sim(file_prefix=str(folder / 'epanet'), version=2.2, convergence_error=True)
            else:
                raw = wntr.sim.WNTRSimulator(model).run_sim(convergence_error=True)
        if raw.error_code:
            raise AnalysisError('Hidrolik çözücü yakınsamadı; bu plan için sonuç üretilemedi.')
        seconds = raw.node['pressure'].index.to_numpy()
        wanted = np.arange(0, scenario.horizon_hours * 3600 + 1, scenario.step_minutes * 60)
        if not np.array_equal(seconds, wanted):
            raise AnalysisError('Hidrolik çözüm eksik zaman adımı döndürdü; sıfırla tamamlanmadı.')
        for frame in [raw.node['pressure'], raw.node['head'], raw.node['demand'], raw.link['flowrate']]:
            if not np.isfinite(frame.to_numpy()).all():
                raise AnalysisError('Hidrolik çıktıda sonlu olmayan değer var; sonuç üretilemedi.')
    except AnalysisError:
        raise
    except Exception as error:
        raise AnalysisError('EPANET hidrolik çözümü tamamlayamadı. Arıza sayısını azaltıp süreleri kontrol edin; ayrıntı deney kaydındadır.') from error
    elapsed = time.perf_counter() - started
    expected = expected.loc[seconds, model.junction_name_list]
    actual = raw.node['demand'][model.junction_name_list]
    # Deficit is a defined customer-withdrawal metric, never a replacement of raw solver data.
    deficit = (expected - actual).where(expected > 0, 0).clip(lower=0)
    weights = np.array([scenario.critical_weights.get(n, 1) for n in model.junction_name_list])
    weighted = deficit.to_numpy() @ weights
    critical = list(scenario.critical_weights)
    low = (raw.node['pressure'][critical] < scenario.low_pressure_m).sum(axis=1) if critical else np.zeros(len(seconds))
    pressures = raw.node['pressure'][model.junction_name_list]
    negative = int((pressures.to_numpy() < -1e-6).sum())
    for key in ['pressure', 'head', 'demand']:
        raw.node[key].to_csv(folder / f'{key}.csv', encoding='utf-8-sig', index_label='zaman_saniye')
    raw.link['flowrate'].to_csv(folder / 'flowrate.csv', encoding='utf-8-sig', index_label='zaman_saniye')
    expected.to_csv(folder / 'expected-demand.csv', encoding='utf-8-sig', index_label='zaman_saniye')
    raw.link['status'].to_csv(folder / 'link-status.csv', encoding='utf-8-sig', index_label='zaman_saniye')
    return {
        'solver': 'EPANET 2.2' if solver == 'epanet' else 'WNTRSimulator',
        'status': 'computed_with_pressure_warning' if negative else 'computed',
        'warnings': ([f'{negative} düğüm/zaman örneğinde negatif basınç var; gerçek değerler korundu.'] if negative else [])
                    + (['Çözücü uyarı verdi; özgün teknik kayıt deney dosyasında saklandı.'] if caught else []),
        'solver_warnings_original': [str(w.message) for w in caught],
        'times_seconds': seconds.tolist(),
        'node_ids': model.node_name_list, 'link_ids': model.link_name_list,
        'pressure_m': raw.node['pressure'][model.node_name_list].to_numpy().tolist(),
        'head_m': raw.node['head'][model.node_name_list].to_numpy().tolist(),
        'demand_m3s': raw.node['demand'][model.node_name_list].to_numpy().tolist(),
        'flowrate_m3s': raw.link['flowrate'][model.link_name_list].to_numpy().tolist(),
        'link_status': raw.link['status'][model.link_name_list].to_numpy().tolist(),
        'expected_customer_demand_m3s': expected.clip(lower=0).sum(axis=1).tolist(),
        'delivered_customer_demand_m3s': actual.where(expected > 0, 0).sum(axis=1).tolist(),
        'unmet_demand_m3s': deficit.sum(axis=1).tolist(),
        'minimum_junction_pressure_m': pressures.min(axis=1).tolist(),
        'metrics': {'unmet_demand_volume_m3': integrate(deficit.sum(axis=1), seconds),
                    'weighted_unmet_volume_m3': integrate(weighted, seconds),
                    'critical_low_pressure_node_hours': integrate(low, seconds) / 3600,
                    'repair_completion_hour': max([a['ends_at_h'] for a in assignments], default=0),
                    'solver_seconds': elapsed},
        'units': {'pressure': 'm', 'head': 'm', 'demand': 'm³/s', 'flowrate': 'm³/s',
                  'unmet_volume': 'm³', 'critical_duration': 'düğüm·saat'},
        'assignments': assignments,
    }
