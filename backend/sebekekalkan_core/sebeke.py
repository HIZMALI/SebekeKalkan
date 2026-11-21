"""Basic crew allocation only; NOT a hydraulic simulator or a water-loss model.

Physical service outcomes MUST come from the validated WNTR / EPANET adapter
in the new project, not from topology or this crew scheduler.
"""
from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class RepairTask:
    pipe_id: str
    hours: float


@dataclass(frozen=True)
class RepairAssignment:
    pipe_id: str
    crew: int
    starts_at_h: float
    ends_at_h: float


def allocate_crews(tasks: Sequence[RepairTask], crew_count: int) -> tuple[RepairAssignment, ...]:
    """Deterministic list scheduling, no hydraulic priority claim."""
    if isinstance(crew_count, bool) or not isinstance(crew_count, int) or not 1 <= crew_count <= 3:
        raise ValueError('Ekip sayısı 1–3 arasında tam sayı olmalı')
    if len({x.pipe_id for x in tasks}) != len(tasks):
        raise ValueError('Yinelenen boru kimliği')
    free=[0.0]*crew_count
    out=[]
    for task in tasks:
        if not task.pipe_id.strip() or not math.isfinite(task.hours) or task.hours <= 0:
            raise ValueError('Onarım girdisi geçersiz')
        crew=min(range(crew_count),key=lambda c:(free[c],c))
        start=free[crew]
        free[crew]+=task.hours
        out.append(RepairAssignment(task.pipe_id,crew,round(start,6),round(free[crew],6)))
    return tuple(out)


def hydraulic_impacts(scenario, assignments, folder, solver='epanet'):
    """Gerçek çözücüye delege eder; topolojik ya da sabit yedek sonuç üretmez."""
    from .hydraulics import simulate
    return simulate(scenario, assignments, folder, solver=solver)
