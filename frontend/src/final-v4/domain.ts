export const API = '/api/final/v2';
export const METRICS = [
  ['weighted_unmet_volume_m3', 'Ağırlıklı hizmet açığı', 'ağırlıklı m³'],
  ['unmet_demand_volume_m3', 'Ağırlıksız hizmet açığı', 'm³'],
  ['critical_low_pressure_node_hours', 'Kritik düşük basınç', 'düğüm·saat'],
  ['repair_completion_hour', 'Son onarım', 'saat'],
] as const;

export const NAMES: Record<string,string> = {
  fifo: 'Bildirim sırası (FIFO)', greedy: 'Güçlü referans', s02_b6: 'ŞebekeKalkan B6',
  proposal: 'ŞebekeKalkan v2', oracle: 'Kapsamlı · 24 sıra', s02_b12: 'ŞebekeKalkan B12',
};

export type Point = [number, number];
export type Diagram = {nodes: Record<string, Point>; pipes: Record<string, Point[]>; other_links: Point[][]};
export type Assignment = {pipe_id: string; crew: number; starts_at_h: number; ends_at_h: number};
export type Method = {order: string[]; assignments: Assignment[]; metrics: Record<string,number>; physics: Record<string,unknown>};
export type Trace = {
  minutes: number[]; node_ids: string[]; pipe_ids: string[]; pressure_m: number[][]; link_status: number[][];
  flow_m3s: number[][]; expected_lps: number[]; delivered_lps: number[]; deficit_lps: number[]; raw_sha256: string;
};
export type RunView = {
  case_id: string; network: string; group: string; mode: string; crews: number; baseline: string; comparison: string;
  failures: string[]; horizon_hours: number; failure_start_hour: number; diagram: Diagram;
  methods: Record<string,Method>; traces: Record<string,Trace>; evidence: Record<string,unknown>;
};
export type Counts = Record<string, number>;
export type Research = {
  groups: Record<string, Counts>; total: Counts; source: string; source_sha256: string;
  gap: {method: string; weighted_unmet_volume_m3: string}[];
  losses: {case:string; metric:string; baseline:string; proposal:string; baseline_value:number; proposal_value:number}[];
};

export function format(value: number, digits = 2, minimum = 0) {
  return new Intl.NumberFormat('tr-TR', {maximumFractionDigits: digits, minimumFractionDigits: minimum}).format(value);
}

export function timestamp(minutes: number) {
  return String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0');
}

export function difference(ref: number, next: number, key: string) {
  const equal = key === 'repair_completion_hour' ? ref === next :
    Math.abs(ref - next) <= 1e-6 + 1e-8 * Math.max(Math.abs(ref), Math.abs(next));
  return equal ? 0 : ref - next;
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, {...init, cache:'no-store'});
  if (!r.ok) {
    const payload: {message?:string} = await r.json().catch(()=>({}));
    throw new Error(payload.message || 'Yerel veri okunamadı.');
  }
  return r.json();
}
