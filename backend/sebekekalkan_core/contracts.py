from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class Failure(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pipe_id: str = Field(min_length=1, max_length=32)
    repair_hours: Annotated[FiniteFloat, Field(gt=0, le=12)]


class Scenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='Müdahale karşılaştırması', min_length=1, max_length=100)
    failures: list[Failure] = Field(min_length=1, max_length=3)
    crews: int = Field(default=2, ge=1, le=3, strict=True)
    failure_start_hour: Annotated[FiniteFloat, Field(ge=0, le=24)] = 2
    horizon_hours: int = Field(default=12, ge=2, le=48, strict=True)
    step_minutes: int = Field(default=15, ge=5, le=60, strict=True)
    required_pressure_m: Annotated[FiniteFloat, Field(ge=1, le=50)] = 20
    low_pressure_m: Annotated[FiniteFloat, Field(gt=0, le=50)] = 15
    hydraulic_trials: int = Field(default=40, ge=1, le=200, strict=True)
    critical_weights: dict[str, Annotated[FiniteFloat, Field(ge=1, le=10)]] = Field(default_factory=lambda: {'101': 3, '109': 2})
    manual_order: list[str] | None = None

    @model_validator(mode='after')
    def consistent(self):
        ids = [f.pipe_id for f in self.failures]
        if len(set(ids)) != len(ids):
            raise ValueError('Aynı boru iki kez arıza olarak seçilemez.')
        if self.step_minutes not in [5, 10, 15, 30, 60]:
            raise ValueError('Örnekleme adımı 5, 10, 15, 30 veya 60 dakika olmalı.')
        if self.failure_start_hour + sum(f.repair_hours for f in self.failures) > self.horizon_hours:
            raise ValueError('Analiz ufku, arıza başlangıcını ve en uzun sıralı onarım süresini kapsamalı.')
        for hours in [self.failure_start_hour, *[f.repair_hours for f in self.failures]]:
            if abs(hours * 60 / self.step_minutes - round(hours * 60 / self.step_minutes)) > 1e-8:
                raise ValueError('Başlangıç ve onarım süreleri seçilen örnekleme adımının katı olmalı.')
        if self.manual_order is not None and (len(self.manual_order) != len(ids) or set(self.manual_order) != set(ids)):
            raise ValueError('Elle belirlenen sıra bütün arızalı boruları yalnız bir kez içermeli.')
        if len(self.critical_weights) > 10:
            raise ValueError('En fazla 10 kritik düğüm tanımlayın.')
        return self
