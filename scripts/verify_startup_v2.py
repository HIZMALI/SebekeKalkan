from pathlib import Path
import uuid
from sebekekalkan_core.contracts_v2 import ScenarioV2
from sebekekalkan_core.hydraulics_v2 import simulate_checked
ROOT=Path(__file__).resolve().parents[1]
scenario=ScenarioV2.model_validate_json((ROOT/'experiments/configs/master_jury.json').read_text(encoding='utf-8'))
folder=ROOT/'.calisma/startups'/uuid.uuid4().hex
result=simulate_checked(scenario,[],folder)
assert result['physical_gate']['pass']
print('WNTR başlangıç bazının depo, kütle dengesi ve talep kapıları geçti. Kullanıcı planları ayrıca tek tek denetlenecek.')
