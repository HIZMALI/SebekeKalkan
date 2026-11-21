import argparse,json
from pathlib import Path
from .contracts_v2 import ScenarioV2
from .planning_v2 import compare_v2
def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=compare_v2(ScenarioV2.model_validate_json(a.config.read_text(encoding='utf-8-sig')),a.output)
    print(json.dumps({'status':'completed','model_version':result['model_version'],'physical_validation':result['physical_validation'],'order':result['decision']['selected']['order']},ensure_ascii=False))
if __name__=='__main__':main()
