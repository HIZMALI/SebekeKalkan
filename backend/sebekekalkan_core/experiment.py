"""Reproducible, process-isolated analysis entry point."""
import argparse
import json
import sys
import uuid
from pathlib import Path

from .contracts import Scenario
from .networks import EVIDENCE
from .planning import compare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    destination = args.output or EVIDENCE / ('run-' + uuid.uuid4().hex)
    result = compare(Scenario.model_validate_json(args.config.read_text(encoding='utf-8-sig')), destination)
    print(json.dumps({'durum': 'tamamlandı', 'deney': str(destination), 'oracle_dogrulandi': result['search']['oracle_verified']}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
