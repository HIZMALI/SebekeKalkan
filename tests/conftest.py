import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(ROOT / '.cache/matplotlib')
os.environ['TEMP'] = os.environ['TMP'] = str(ROOT / '.cache/tmp')
Path(os.environ['TEMP']).mkdir(parents=True, exist_ok=True)

import pytest
from sebekekalkan_core.contracts import Scenario


@pytest.fixture
def scenario():
    return Scenario.model_validate_json((ROOT/'experiments/configs/example.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='session')
def comparison(tmp_path_factory):
    from sebekekalkan_core.planning import compare
    value = Scenario.model_validate_json((ROOT/'experiments/configs/example.json').read_text(encoding='utf-8'))
    folder = tmp_path_factory.mktemp('comparison')
    return compare(value, folder), folder
