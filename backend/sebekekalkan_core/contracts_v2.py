"""EPANET denemesi ve WNTR Newton yinelemesi farklı, sürümlü ayarlardır."""
from pydantic import Field
from .contracts import Scenario
class ScenarioV2(Scenario):
    wntr_max_iterations:int=Field(default=3000,ge=1,le=3000,strict=True)
