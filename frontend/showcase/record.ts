import {format} from '../src/final-v4/domain';
import type {Diagram, Point, Trace} from '../src/final-v4/domain';
import type {PipeMark} from '../src/final-v4/NetworkStage';
import proof from '../../data/demo/kanit.json';

export {proof};
export const {net, mu, study} = proof;
export const plans = ['greedy', 's02_b6'] as const;
export type Plan = (typeof plans)[number];
export const planNames: Record<Plan, string> = {greedy:'Güçlü referans', s02_b6:'ŞebekeKalkan'};
export const timeline = net.traces.greedy.minutes;
export const isolationMinute = Math.min(...net.methods.greedy.assignments.map(item => item.starts_at_h * 60));
export const lastRepairMinute = Math.max(...plans.map(plan => net.methods[plan].metrics.repair_completion_hour)) * 60;
export const lastMinute = timeline[timeline.length - 1];
export const clock = (minute: number) => [Math.floor(minute / 60), minute % 60].map(part => String(part).padStart(2, '0')).join('.');
export const num = (value: number, digits = 2) => format(value, digits, digits);

const point = ([x, y]: number[]): Point => [x, y];
export const diagram: Diagram = {
  nodes: Object.fromEntries(Object.entries(net.diagram.nodes).map(([id, points]) => [id, point(points)])),
  pipes: Object.fromEntries(Object.entries(net.diagram.pipes).map(([id, points]) => [id, points.map(point)])),
  other_links: (net.diagram.other_links as number[][][]).map(points => points.map(point)),
};

export const statusLabels: Record<string, string> = {
  pending: 'Arıza öncesi · açık',
  fault: 'Arızalı · kapalı',
  work: 'Onarım sürüyor · kapalı',
  repaired: 'Onarıldı · açık',
};

export function marksAt(plan: Plan, step: number) {
  const trace: Trace = net.traces[plan];
  const minute = timeline[step];
  return Object.fromEntries(net.methods[plan].assignments.map((repair, index) => {
    const open = trace.link_status[step][trace.pipe_ids.indexOf(repair.pipe_id)] !== 0;
    const kind = minute < isolationMinute ? 'pending' : open ? 'repaired' : minute >= repair.starts_at_h * 60 ? 'work' : 'fault';
    return [repair.pipe_id, {kind, label:repair.pipe_id, description:`Öncelik ${index + 1}`} satisfies PipeMark];
  }));
}

export function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadDemandCsv() {
  const heading = 'Kayıt;Yöntem;Dakika;Karşılanan müşteri talebi (L/s);Beklenen (L/s);Eksik (L/s);Ham SHA-256';
  const rows = plans.flatMap(plan => {
    const values = net.traces[plan];
    return timeline.map((time, i) => [net.run, plan, time, values.delivered_lps[i], values.expected_lps[i],
      values.deficit_lps[i], values.raw_sha256].join(';'));
  });
  download('SebekeKalkan-Net2-G4-C1-zaman-serisi.csv', '\ufeff' + [heading, ...rows].join('\r\n'), 'text/csv;charset=utf-8');
}
