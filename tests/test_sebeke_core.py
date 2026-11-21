import pytest
from sebekekalkan_core.sebeke import RepairTask, allocate_crews, hydraulic_impacts


def test_crew_assignment_no_overlap():
    out=allocate_crews([RepairTask('P1',2),RepairTask('P2',1),RepairTask('P3',3)],2)
    assert len(out)==3
    assert out[0].crew==0 and out[0].ends_at_h==2
    assert out[1].crew==1 and out[1].ends_at_h==1
    assert out[2].crew==1 and out[2].starts_at_h==1


def test_hydraulic_calculation_is_real(tmp_path):
    from sebekekalkan_core.contracts import Scenario
    scenario = Scenario(failures=[{'pipe_id':'137','repair_hours':1}], horizon_hours=4)
    result = hydraulic_impacts(scenario, [], tmp_path/'physical')
    assert result['solver'] == 'EPANET 2.2'
    assert len(result['pressure_m']) == 17
    assert (tmp_path/'physical/epanet.rpt').is_file()
