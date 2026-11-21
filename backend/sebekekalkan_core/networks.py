"""Pinned complete engineering model. No archive or topology-CSV input path."""
from pathlib import Path
import hashlib
import json

import wntr

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'data/networks/Net3.inp'
EVIDENCE = ROOT / 'experiments/results/build01'
MANIFEST = ROOT / 'data/metadata/net3.json'


class AnalysisError(ValueError):
    """A visible, actionable Turkish analysis failure."""


def load_model():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != manifest['sha256']:
        raise AnalysisError('Doğrulanmış ağ dosyasının özeti değişmiş. Kaynak Net3 dosyasını geri yükleyin.')
    return wntr.network.WaterNetworkModel(str(MODEL))


def eligible_pipes(model):
    controlled = {obj.name for _, control in model.controls() for obj in control.requires()
                  if hasattr(obj, 'start_node_name')}
    return {name for name, pipe in model.pipes() if name not in controlled
            and not pipe.check_valve and str(pipe.initial_status) == 'Open'}


def network_data():
    model = load_model()
    eligible = eligible_pipes(model)
    return {
        'id': 'Net3', 'name': 'Net3 — açık mühendislik test ağı',
        'provenance': json.loads(MANIFEST.read_text(encoding='utf-8')),
        'inventory': {'nodes': model.num_nodes, 'junctions': model.num_junctions,
                      'pipes': model.num_pipes, 'pumps': model.num_pumps,
                      'tanks': model.num_tanks, 'reservoirs': model.num_reservoirs,
                      'controls': model.num_controls, 'patterns': model.num_patterns},
        'nodes': [{'id': name, 'kind': node.node_type, 'x': node.coordinates[0],
                   'y': node.coordinates[1], 'base_demand_m3s': getattr(node, 'base_demand', 0)}
                  for name, node in model.nodes()],
        'links': [{'id': name, 'kind': link.link_type, 'start': link.start_node_name,
                   'end': link.end_node_name, 'length_m': getattr(link, 'length', None),
                   'eligible': name in eligible,
                   'exclusion': '' if name in eligible else 'Özgün kontrol, çekvalf veya boru dışı bağlantı'}
                  for name, link in model.links()],
        'coordinate_notice': 'Özgün modelin şematik koordinatlarıdır; Balıkesir veya gerçek şehir haritası değildir.',
    }
