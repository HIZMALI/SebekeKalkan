import ctypes,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
from sebekekalkan_core.networks import ROOT
R1=ROOT/'experiments/results/build02_r1'

def test_empty_tank_event_has_outflow_and_balance_violation_only_in_epanet():
    summary=json.loads((R1/'diagnostics/summary.json').read_text(encoding='utf-8'))
    a=summary['epanet']['tanks']['2'];b=summary['wntr']['tanks']['2']
    assert a['first_min_contact_s']==b['first_min_contact_s']
    assert 5*3600<a['first_min_contact_s']<6.5*3600
    tanks=pd.read_csv(R1/'diagnostics/tank_events.csv',sep=';');links=pd.read_csv(R1/'diagnostics/link_events.csv',sep=';')
    at=a['first_min_contact_s']
    for solver in ['epanet','wntr']:
        tank=tanks[(tanks.motor==solver)&(tanks.depo==2)&(tanks.zaman_s==at)].iloc[0]
        link=links[(links.motor==solver)&(links.baglanti==50)&(links.zaman_s==at)].iloc[0]
        assert abs(tank.seviye_m-tank.min_seviye_m)<.001
        if solver=='epanet':assert link.durum==1 and link.isaretli_debi_m3s>1e-6
        else:assert link.durum==0 and abs(link.isaretli_debi_m3s)<1e-7
    assert not a['mass_balance_pass'] and not a['minimum_outflow_pass']
    assert b['mass_balance_pass'] and b['minimum_outflow_pass']

def test_primary_wntr_all_tank_mass_bounds_pdd_and_events_pass():
    result=json.loads((R1/'diagnostics/physical-gates.json').read_text(encoding='utf-8'))
    assert result['wntr']['pass']
    assert not result['epanet']['pass']
    assert len(result['wntr']['tanks'])==3

def test_denser_observation_did_not_change_hydraulics():
    s=json.loads((R1/'diagnostics/summary.json').read_text(encoding='utf-8'))
    assert max(s['wntr']['observation_matches_report'].values())<1e-8
    # Toolkit values retain double precision; EPANET binary report has float32 precision.
    assert s['epanet']['observation_matches_report']['pressure_m']<1e-4

def test_controls_do_not_target_same_link():
    c=json.loads((R1/'diagnostics/control_conflicts.json').read_text(encoding='utf-8'))
    assert not c['direct_conflict_found'] and not c['shared_targets']

def test_loaded_binary_version_and_content_are_recorded():
    from wntr.epanet.toolkit import ENepanet
    old=json.loads((R1/'binary-provenance.json').read_text(encoding='utf-8'))['epanet_dll']
    ep=ENepanet(version=2.2);path=Path(ep.ENlib._name)
    assert path.is_relative_to(ROOT)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==old['sha256']
    v=ctypes.c_int();ep.ENlib.ENgetversion.argtypes=[ctypes.POINTER(ctypes.c_int)];ep.ENlib.ENgetversion.restype=ctypes.c_int
    assert ep.ENlib.ENgetversion(ctypes.byref(v))==0
    assert v.value==old['ENgetversion_integer']==20200
