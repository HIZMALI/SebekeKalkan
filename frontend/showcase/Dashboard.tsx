import type {CSSProperties, RefObject} from 'react';
import NetworkStage, {BANDS} from '../src/final-v4/NetworkStage';
import type {Trace} from '../src/final-v4/domain';
import {
  clock, diagram, download, downloadDemandCsv, isolationMinute, lastMinute, lastRepairMinute, marksAt,
  net, num, planNames, plans, proof, statusLabels, timeline,
} from './record';
import type {Plan} from './record';

type DashboardProps = {
  plan: Plan; step: number; playing: boolean; speed: number; inspected: string | null; jury: boolean;
  onPlan: (plan: Plan) => void; onMove: (minute: number) => void; onPlay: () => void;
  onSpeed: (speed: number) => void; onInspect: (id: string | null) => void;
  onExit: () => void; exitRef: RefObject<HTMLButtonElement | null>;
};
export const playbackSpeeds = [.5, 1, 2, 4];
const presets = [isolationMinute, 480, lastRepairMinute];
const demandScale = Math.ceil(Math.max(...plans.flatMap(plan => net.traces[plan].delivered_lps)) / 5) * 5;

function Comparison({plan, step}: {plan: Plan; step: number}) {
  const minute = timeline[step];
  const delta = Number((net.traces.s02_b6.delivered_lps[step] - net.traces.greedy.delivered_lps[step]).toFixed(2));
  const expected = net.traces.s02_b6.expected_lps[step];
  const unmet = expected > 0 && plans.every(id => net.traces[id].delivered_lps[step] === 0);
  const amount = `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${num(Math.abs(delta))} L/s`;
  const note = minute === 480 ? 'Aynı anda saniyede yaklaşık 2 litre daha fazla su talebi karşılanıyor.'
    : unmet ? `Kayıtta iki plan da ${num(expected)} L/s talebi karşılayamıyor.`
    : delta === 0 ? 'Gösterilen hassasiyette iki plan eşit.'
    : delta > 0 ? 'Bu saatte ŞebekeKalkan planı daha fazla talebi karşılıyor.'
    : 'Bu saatte güçlü referans daha fazla talebi karşılıyor.';

  return <aside className="comparison" aria-labelledby="comparison-title">
    <div className="comparison-heading">
      <div><p className="eyebrow">Seçili zaman</p><h2 id="comparison-title">Karşılanan su talebi</h2></div>
      <span className="comparison-clock">{clock(minute)}</span>
    </div>
    <dl className="demand-pair">
      {plans.map(id => {
        const demand = net.traces[id].delivered_lps[step];
        return <div className={`demand-row demand-row--${id}`} key={id} data-active={plan === id}>
          <dt>{planNames[id]}</dt>
          <dd data-testid={`demand-${id}`}>{num(demand)} <span className="demand-unit">L/s</span>
            <span className="demand-track" aria-hidden="true"><span style={{width:`${100 * demand / demandScale}%`}}/></span>
          </dd>
        </div>;
      })}
    </dl>
    <div className="instant-difference">
      <strong data-testid="instant-difference">{amount}</strong>
      <p>{note}</p>
    </div>
    <div className="whole-run">
      <div>
        <p className="eyebrow">Tüm süreç</p>
        <div className="whole-metric"><strong data-testid="main-gain">%{num(net.percent)}</strong><span>daha düşük ağırlıklı hizmet açığı</span></div>
      </div>
      <div className="conditions">
        <span>Aynı ekip ve onarım süreleri</span>
        <strong>İki plan da {lastRepairMinute / 60}. saatte bitiyor</strong>
      </div>
    </div>
    <details className="metric-help">
      <summary>Hizmet açığı nedir?</summary>
      <p>Simülasyonun 24 saati boyunca karşılanamayan su talebi toplanır ve öncelikli düğümlere daha fazla ağırlık verilir.</p>
      <p>Kritik düşük basınç: {num(net.methods.greedy.metrics.critical_low_pressure_node_hours, 1)} → {num(net.methods.s02_b6.metrics.critical_low_pressure_node_hours, 1)} düğüm-saat.</p>
    </details>
  </aside>;
}

function Playback({step, playing, speed, onMove, onPlay, onSpeed}: Pick<DashboardProps, 'step' | 'playing' | 'speed' | 'onMove' | 'onPlay' | 'onSpeed'>) {
  const minute = timeline[step];
  return <div className="playback" aria-label="Zaman kontrolü">
    <div className="playback-row">
      <button className="play-control" type="button" aria-label={playing?'Zamanı duraklat':'Zamanı oynat'} onClick={onPlay}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          {playing?<path d="M9 5v14m6-14v14"/>:<path d="m9 5 10 7-10 7z"/>}
        </svg>
        {playing?'Duraklat':'Oynat'}
      </button>
      <label className="speed-control"><span>Hız</span>
        <select aria-label="Oynatma hızı" value={speed} onChange={event=>onSpeed(Number(event.target.value))}>
          {playbackSpeeds.map(value=><option key={value} value={value}>{formatSpeed(value)}×</option>)}
        </select>
      </label>
      <button type="button" className="reset-time" aria-label="Başlangıca dön" onClick={()=>onMove(timeline[0])}>Başlangıç</button>
      {presets.map(at=><button type="button" className="time-preset" key={at} aria-pressed={minute === at}
        onClick={()=>onMove(at)}>{at === lastRepairMinute?'Son onarım':clock(at)}</button>)}
    </div>
    <label className="visually-hidden" htmlFor="time">Simülasyon zamanı</label>
    <input id="time" type="range" min="0" max={timeline.length - 1} value={step} aria-valuetext={clock(minute)}
      onChange={event=>onMove(timeline[Number(event.target.value)])}
      style={{'--playhead':`${100 * minute / lastMinute}%`} as CSSProperties}/>
    <div className="range-hours" aria-hidden="true"><span>00.00</span><span>06.00</span><span>12.00</span><span>18.00</span><span>24.00</span></div>
  </div>;
}

function formatSpeed(value: number) {
  return num(value, Number.isInteger(value)?0:1);
}

export function Dashboard({plan, step, playing, speed, inspected, jury, onPlan, onMove, onPlay, onSpeed,
  onInspect, onExit, exitRef}: DashboardProps) {
  const minute = timeline[step];
  const trace: Trace = net.traces[plan];
  const marks = marksAt(plan, step);
  const pressures = Object.fromEntries(trace.node_ids.map((id, index)=>[id, trace.pressure_m[step][index]]));
  const assignment = inspected && net.methods[plan].assignments.find(item=>item.pipe_id === inspected);
  const repaired = Object.values(marks).filter(mark=>mark.kind === 'repaired').length;

  return <div className="dashboard" data-mode={proof.mode}>
    {jury&&<div className="jury-bar">
      <div><strong>ŞebekeKalkan</strong><span>Jüri modu · Kayıtlı gösterim</span></div>
      <p>← → zamanı değiştirir <span>·</span> 2 / 8 saat seçer <span>·</span> Esc çıkar</p>
      <button type="button" ref={exitRef} onClick={onExit}>Jüri modundan çık</button>
    </div>}
    <div className="network-panel">
      <header className="panel-heading">
        <div><h2>Net2 şebekesi</h2><p>Dört arıza · Bir ekip</p></div>
        <output htmlFor="time" aria-live="off" data-testid="time-label">{clock(minute)}</output>
      </header>
      <div className="mode-switch" role="group" aria-label="Gösterilen onarım planı">
        {plans.map(id=><button key={id} type="button" aria-pressed={plan === id} onClick={()=>onPlan(id)}>{planNames[id]}</button>)}
      </div>
      <NetworkStage diagram={diagram} name="Net2" pressures={pressures} marks={marks}
        inspectedPipe={inspected} onInspect={onInspect}/>
      <div className="pipe-inspector" aria-label="Boru durumu" data-testid="pipe-inspector">
        {inspected ? <>
          <div>
            <strong>Boru {inspected}</strong>
            {assignment ? <><span className={`pipe-state pipe-state--${marks[inspected].kind}`}>{statusLabels[marks[inspected].kind]}</span>
              <span className="pipe-window">{clock(assignment.starts_at_h * 60)}–{clock(assignment.ends_at_h * 60)} · Ekip {assignment.crew}</span></>
              : <span>Bu boru için ayrı bir durum kaydı yok.</span>}
          </div>
          <button type="button" onClick={()=>onInspect(null)}>Kapat</button>
        </> : <><strong>{repaired}/{net.faults.length} boru onarıldı</strong><span>Durumunu görmek için bir boru seçin.</span></>}
      </div>
      <div className="legend" aria-label="Düğüm basıncı ve boru durumu">
        <strong>Basınç</strong>
        {BANDS.map(([key, label])=><span key={key} className={key}><i aria-hidden="true"/>{label}</span>)}
        <span className="pipe-key pipe-key--fault"><i aria-hidden="true"/>Arızalı</span>
        <span className="pipe-key pipe-key--work"><i aria-hidden="true"/>Onarımda</span>
        <span className="pipe-key pipe-key--fixed"><i aria-hidden="true"/>Onarıldı</span>
      </div>
      <Playback step={step} playing={playing} speed={speed} onMove={onMove} onPlay={onPlay} onSpeed={onSpeed}/>
    </div>
    <div className="dashboard-side">
      <Comparison plan={plan} step={step}/>
      {jury&&<Schedule step={step} plan={plan} compact/>}
    </div>
  </div>;
}

export function Schedule({step, plan, compact = false}: {step: number; plan: Plan; compact?: boolean}) {
  const minute = timeline[step];
  const percentage = (value: number) => `${100 * value / lastMinute}%`;
  return <section className={compact?'schedule schedule--compact':'section schedule'} aria-labelledby="schedule-title">
    <div className="section-heading">
      <div><h2 id="schedule-title">Onarım çizelgesi</h2>{!compact&&<p>Her çubuk, borunun gerçek kayıtlı onarım aralığını gösterir.</p>}</div>
      <span className="schedule-time">{!compact&&'Seçili zaman '}<strong>{clock(minute)}</strong></span>
    </div>
    <div className="gantt">
      <div className="gantt-scale" aria-hidden="true">
        {[0, 240, 480, 720, 960, 1200, lastMinute].map(at=><span key={at}>{clock(at)}</span>)}
      </div>
      {plans.map(id=><div className={`gantt-row gantt-row--${id}`} key={id} data-active={id === plan}>
        <h3>{planNames[id]}</h3>
        <div className="gantt-band">
          <ol className="gantt-track" aria-label={planNames[id] + ' onarım aralıkları'}>
            {net.methods[id].assignments.map(item=>{
              const start = item.starts_at_h * 60, end = item.ends_at_h * 60;
              const status = minute >= end ? 'completed' : minute >= start ? 'active' : 'waiting';
              return <li key={item.pipe_id} data-pipe-id={item.pipe_id} data-start={start} data-end={end} data-repair-status={status}
                style={{left:percentage(start), width:percentage(end - start)}}
                title={`Boru ${item.pipe_id}, ${clock(start)}–${clock(end)}`}>
                <span aria-hidden="true">{item.pipe_id}</span>
                <span className="visually-hidden">Boru {item.pipe_id}, {clock(start)} ile {clock(end)} arası</span>
              </li>;
            })}
          </ol>
          <span className="gantt-cursor" aria-hidden="true" style={{left:percentage(minute)}}/>
        </div>
      </div>)}
    </div>
    {!compact&&<><p className="schedule-note">Şema, Net2 test ağına aittir. Renkler seçili kayıttaki düğüm basıncını gösterir.</p>
    <details className="evidence-details">
      <summary>Vaka kaynağı ve indirmeler</summary>
      <dl>
        <dt>Net2 vaka kodu</dt><dd>{net.id}</dd><dt>Kayıt kimliği</dt><dd><code>{net.run}</code></dd>
        <dt>Sonuç SHA-256</dt><dd><code>{net.sha256}</code></dd>
        <dt>Karşılaştırma</dt><dd>Güçlü tekli etki/süre yöntemi ve ŞebekeKalkan B6.</dd>
        {plans.map(id=><div key={id}><dt>{planNames[id]} ham SHA-256</dt><dd><code>{net.traces[id].raw_sha256}</code></dd></div>)}
      </dl>
      <div className="actions">
        <button type="button" onClick={downloadDemandCsv}>Zaman serisi CSV</button>
        <button type="button" onClick={()=>download('SebekeKalkan-dogrulanmis-kayit.json', JSON.stringify(proof, null, 2), 'application/json')}>Kanıt JSON</button>
      </div>
    </details></>}
  </section>;
}
