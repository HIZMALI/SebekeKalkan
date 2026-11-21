import {useEffect, useState} from 'react';
import NetworkStage, {band, BANDS} from './NetworkStage';
import type {PipeMark} from './NetworkStage';
import {difference, format, METRICS, NAMES, timestamp} from './domain';
import type {RunView} from './domain';

export const PRIMARY = METRICS[0][0];
const CRITICAL = METRICS[2][0], FINISH = METRICS[3][0];

function MethodButtons({data, selected, choose}:{data:RunView;selected:string;choose:(id:string)=>void}) {
  return <div className="v4-switch" aria-label="Görüntülenen plan">
    {[...new Set([data.comparison, data.baseline])].map(id=>
      <button key={id} type="button" aria-pressed={id===selected} onClick={()=>choose(id)}>{NAMES[id]}</button>)}
    {selected!==data.comparison&&selected!==data.baseline&&<span>{NAMES[selected]}</span>}
  </div>;
}

export function TraceWorkbench({data}:{data:RunView}) {
  const [methodId,setMethodId]=useState(data.comparison);
  const [index,setIndex]=useState(data.failure_start_hour*4);
  const [play,setPlay]=useState(false);
  const [rate,setRate]=useState(1);
  const trace=data.traces[methodId], method=data.methods[methodId];
  const end=trace.minutes.length-1;
  const running=play&&index<end;
  const time=trace.minutes[index];
  const hour=time/60;
  useEffect(()=>{
    if(!running) return;
    const timer=window.setInterval(()=>setIndex(i=>Math.min(i+1,end)),600/rate);
    return ()=>window.clearInterval(timer);
  },[running,rate,end]);
  const pressures=Object.fromEntries(trace.node_ids.map((id,i)=>[id,trace.pressure_m[index][i]]));
  const marks:Record<string,PipeMark>={};
  const repairs=method.assignments.map(a=>{
    const i=trace.pipe_ids.indexOf(a.pipe_id);
    const closed=trace.link_status[index][i]===0;
    const work=closed&&hour>=a.starts_at_h&&hour<a.ends_at_h;
    const kind=closed?(work?'work':'fault'):(hour>=a.ends_at_h?'repaired':'pending');
    const state=closed?(work?`Ekip ${a.crew} onarıyor`:'Kapalı, ekip bekliyor'):(kind==='repaired'?'Onarıldı, açık':'Arıza öncesi, açık');
    marks[a.pipe_id]={kind,label:String(method.order.indexOf(a.pipe_id)+1),
      description:`${state}, ${format(trace.flow_m3s[index][i]*1000,4)} L/s`};
    return {...a,state};
  });
  function changeIndex(next:number) {
    setPlay(false);
    setIndex(Math.max(0,Math.min(end,next)));
  }
  function togglePlay() {
    if(running){setPlay(false);return;}
    if(index>=end)setIndex(0);
    setPlay(true);
  }
  return <section className="v4-panel v4-workbench" aria-labelledby="v4-pressure">
    <div className="v4-panel-head"><div><h2 id="v4-pressure">Basınç ve onarım</h2>
      <p>{data.network} · {data.failures.length} arıza · {data.crews} ekip</p></div>
      <MethodButtons data={data} selected={methodId} choose={setMethodId}/>
    </div>
    <div className="v4-hydraulic">
      <NetworkStage diagram={data.diagram} name={data.network} marks={marks} pressures={pressures}/>
      <div className="v4-frame">
        <div className="v4-frame-time"><span>Simülasyon saati</span><strong>{timestamp(time)}</strong></div>
        <div className="v4-service-now"><span>Karşılanan müşteri talebi</span>
          <strong>{format(trace.delivered_lps[index],2,2)} <small>L/s</small></strong>
          <span>Talep {format(trace.expected_lps[index],2,2)} L/s</span></div>
        <ul className="v4-frame-pipes" aria-label="Boru ve ekip durumu">
          {repairs.map(a=><li key={a.pipe_id} className={marks[a.pipe_id].kind}>
            <strong><span className="v4-pipe-order" aria-label={`Öncelik ${marks[a.pipe_id].label}`}>{marks[a.pipe_id].label}</span> Boru {a.pipe_id}</strong>
            <span>{a.state}</span></li>)}
        </ul>
      </div>
    </div>
    <div className="v4-band-row" aria-label="Düğüm basıncı görünümü">
      {BANDS.map(([key,label])=><span key={key}><i className={key}/>{label} <b>{Object.values(pressures).filter(p=>band(p)===key).length}</b></span>)}
    </div>
    <div className="v4-transport">
      <button className="v4-primary" type="button" onClick={togglePlay}>{running?'Duraklat':'Oynat'}</button>
      <div className="v4-range"><label htmlFor="v4-time">Zaman</label>
        <input type="range" id="v4-time" min={0} max={end} step={1} value={index}
          aria-valuetext={timestamp(time)} onChange={e=>changeIndex(Number(e.currentTarget.value))}/>
        <span>00:00</span><span>24:00</span></div>
      <label className="v4-rate">Hız <select value={rate} onChange={e=>setRate(Number(e.target.value))}>
        <option value={0.5}>0,5×</option><option value={1}>1×</option><option value={2}>2×</option></select></label>
    </div>
    <div className="v4-gantt" aria-label="Ekip zaman çizelgesi">
      {Array.from({length:data.crews},(_,i)=>i+1).map(crew=><div key={crew} className="v4-lane">
        <b>Ekip {crew}</b><div className="v4-track">
          {method.assignments.filter(a=>a.crew===crew).map(a=><span key={a.pipe_id}
            style={{left:`${a.starts_at_h/24*100}%`,width:`${(a.ends_at_h-a.starts_at_h)/24*100}%`}}
            title={`Boru ${a.pipe_id} · ${a.starts_at_h}–${a.ends_at_h}. saat`}>
            <span className="v4-sr">{`Boru ${a.pipe_id}, ${a.starts_at_h}–${a.ends_at_h}. saat`}</span>
            <span aria-hidden="true">{a.pipe_id}</span></span>)}
          <i style={{left:`${hour/24*100}%`}} aria-hidden="true"/></div></div>)}
    </div>
    <p className="v4-muted v4-schematic-note">Model şeması coğrafi harita değildir. Rota, seyahat süresi ve vana izolasyonu hesaplanmaz.</p>
    <details className="v4-details">
      <summary>Plan seçimi ve anlık ham değerler</summary>
      <p>INP şeması, en boy oranı korunarak ekrana sığdırılır ve gerekirse döndürülür.</p>
      <label className="v4-inline">Görüntülenen plan <select value={methodId} onChange={e=>setMethodId(e.target.value)}>
        {Object.keys(data.methods).map(id=><option value={id} key={id}>{NAMES[id]}</option>)}</select></label>
      <div className="v4-data-grid"><ul>{repairs.map(a=><li key={a.pipe_id}>{marks[a.pipe_id].description} · boru {a.pipe_id}</li>)}</ul>
        <ul className="v4-node-values">{Object.entries(pressures).map(([id,p])=><li key={id}>Düğüm {id} · {format(p,8)} m</li>)}</ul></div>
    </details>
  </section>;
}

function Order({title, order, recommended=false}:{title: string;order: string[];recommended?:boolean}) {
  return <div className={'v4-order'+(recommended?' is-best':'')}>
    <span>{title}</span><ol aria-label={title+' onarım sırası'}>
      {order.map(pipe=><li key={pipe}>{pipe}</li>)}</ol>
  </div>;
}

export function Decision({data}:{data:RunView}) {
  const ref=data.methods[data.baseline], chosen=data.methods[data.comparison];
  const a=ref.metrics[PRIMARY], b=chosen.metrics[PRIMARY], diff=difference(a,b,PRIMARY);
  const primaryCase=data.mode==='recorded'&&data.case_id==='Net2_G4_C1'&&
    data.group==='internal_holdout'&&data.baseline==='greedy'&&data.comparison==='s02_b6';
  const pct=primaryCase&&a>0&&diff>0?100*diff/a:null;
  const roundedDelta=Math.abs(diff)<.005?'0,01’den az':format(Math.abs(diff),2,2);
  const display=diff===0?'Eşit':pct!==null?`%${format(pct,2,2)}`:diff>0?'Daha az açık':'Daha fazla açık';
  const finish1=ref.metrics[FINISH],finish2=chosen.metrics[FINISH];
  return <section className="v4-panel v4-decision" aria-labelledby="v4-decision">
    <div className="v4-panel-head"><div><h2 id="v4-decision">Onarım sıralarının karşılaştırması</h2>
      {data.mode==='recorded'&&<p>{data.case_id} · {primaryCase?'Net2 iç değerlendirme':'Skeletonize dış değerlendirme'}</p>}
      <p>{NAMES[data.comparison]} · {NAMES[data.baseline]} ile kıyas</p></div></div>
    <div className="v4-main-number">
      <span>Ağırlıklı hizmet açığı</span>
      <strong className={diff!==0&&pct===null?'v4-word-result':undefined}>{display}</strong>
      <p>{diff===0?`${format(b,2,2)} ağırlıklı m³ · iki yöntemde`:
        `${roundedDelta} ağırlıklı m³ ${diff>0?'daha az':'daha fazla'} açık`}</p>
      <small>{format(a,2,2)} → {format(b,2,2)} ağırlıklı m³</small>
    </div>
    <Order title={NAMES[data.baseline]} order={ref.order}/>
    <Order title={NAMES[data.comparison]} order={chosen.order} recommended/>
    <div className="v4-mini-grid">
      <div><span>Ağırlıksız hizmet açığı</span><strong>{format(ref.metrics[METRICS[1][0]])} → {format(chosen.metrics[METRICS[1][0]])}</strong><small>m³</small></div>
      <div><span>Kritik düşük basınç</span><strong>{format(ref.metrics[CRITICAL])} → {format(chosen.metrics[CRITICAL])}</strong><small>düğüm·saat</small></div>
      <div><span>Son onarım</span><strong>{format(finish1)} saat {finish1===finish2?'=':'→'} {format(finish2)} saat</strong></div>
    </div>
    <p className="v4-note">Ağırlıklı m³, modelde müşteri hizmet açığına verilen önceliği içerir. Saha su tasarrufu ölçülmedi.</p>
    <details className="v4-details"><summary>Bildirim sırasına bak</summary>
      <Order title={NAMES.fifo} order={data.methods.fifo.order}/>
      <p>Ağırlıklı açık {format(data.methods.fifo.metrics[PRIMARY],2,2)} ağırlıklı m³.</p>
    </details>
  </section>;
}

export function Alternatives({data}:{data:RunView}) {
  const chosen=data.methods[data.comparison];
  const compare=Object.entries(data.methods);
  const costs=compare.flatMap(([id,m])=>id===data.comparison?[]:METRICS.slice(1).flatMap(([key,label,unit])=>{
    const change=difference(m.metrics[key],chosen.metrics[key],key);
    return change<0?[{id,label,unit,delta:-change}]:[];
  }));
  return <section className="v4-panel" id="v4-alternatives">
    <h2>Alternatifler</h2><p>Aynı arızalar, aynı ekip sayısı, aynı 24 saat. Dört ölçütte küçük değer tercih edilir.</p>
    <div className="v4-plan-grid">{compare.map(([id,m])=>
      <article key={id} className={id===data.comparison?'is-best':''}><h3>{NAMES[id]}</h3>
        <p>{m.order.join(' → ')}</p>
        <dl>{METRICS.map(([key,label,unit])=><div key={key}><dt>{label}</dt>
          <dd>{format(m.metrics[key],8)} {unit}</dd></div>)}</dl>
      </article>)}</div>
    {costs.length>0&&<div className="v4-warn"><strong>Önerilen planın bedelleri</strong><ul>
      {costs.map(row=><li key={row.id+row.label}>{NAMES[row.id]} ile kıyaslandığında {row.label.toLocaleLowerCase('tr-TR')}, {format(row.delta,6)} {row.unit} daha yüksek.</li>)}
    </ul></div>}
    <details className="v4-details"><summary>Gerekçe</summary>
      <p>Karar önce ağırlıklı hizmet açığına, sonra kritik düşük basınç ve son onarım saatine bakar. Küçük sayısal farklara ön kayıtlı eşitlik toleransı uygulanır. Ağırlıksız hacim sonuçta ayrıca gösterilir.</p>
      {data.methods.s02_b6&&<p>B6, en çok altı aday çizelgeyi çözer. Bildirim sırası ve güçlü referans aday havuzuna zorunlu girer. Güçlü referans her borunun tekli etkisini onarım süresine böler.</p>}
    </details>
  </section>;
}

export function ServiceChart({data}:{data:RunView}) {
  const [delta,setDelta]=useState(false);
  const reference=data.traces[data.baseline], proposed=data.traces[data.comparison];
  const diffs=reference.deficit_lps.map((v,i)=>v-proposed.deficit_lps[i]);
  const curves=delta?[diffs]:[reference.deficit_lps, proposed.deficit_lps];
  const lo=Math.min(0,...curves.flat()), hi=Math.max(0,...curves.flat()), span=hi-lo||1;
  const x=(t:number)=>58+t/1440*680;
  const y=(value:number)=>172-(value-lo)/span*141;
  const color=delta?['#006c65']:['#596e9a','#006c65'];
  return <section className="v4-panel" aria-labelledby="v4-service">
    <div className="v4-panel-head"><div><h2 id="v4-service">Hizmet açığı zaman serisi</h2>
      <p>{delta?'Güçlü referans eksi önerilen plan. Pozitif değer, o adımda daha az açık demektir.':
        'Karşılanmayan toplam müşteri debisi. Her adım 15 dakika.'}</p></div>
      <div className="v4-switch"><button type="button" aria-pressed={!delta} onClick={()=>setDelta(false)}>İki plan</button>
        <button type="button" aria-pressed={delta} onClick={()=>setDelta(true)}>Debi farkı</button></div></div>
    <svg className="v4-series" viewBox="0 0 760 205" role="img" aria-label={delta?'İki planın debi farkı, L/s':'İki plan için hizmet açığı, L/s'}>
      {[...new Set([lo,0,hi])].map(v=><g key={v}><path d={`M58 ${y(v)} H738`} stroke="#cddade"/>
        <text x="51" y={y(v)+4} textAnchor="end">{format(v,2)}</text></g>)}
      {[0,360,720,1080,1440].map(t=><text key={t} x={x(t)} y={194} textAnchor="middle">{timestamp(t)}</text>)}
      <text x="58" y="17">L/s</text>
      {curves.map((curve,i)=><path key={i} data-curve={delta?'reference-minus-proposal':i===0?data.baseline:data.comparison}
        d={curve.map((v,step)=>step?`H ${x(reference.minutes[step])} V ${y(v)}`:`M ${x(0)} ${y(v)}`).join(' ')}
        fill="none" stroke={color[i]} strokeDasharray={i===0&&!delta?'5 3':undefined} strokeWidth="2.5" vectorEffect="non-scaling-stroke"/>)}
    </svg>
    {!delta&&<p className="v4-series-label"><span>{NAMES[data.baseline]} (kesikli)</span><span>{NAMES[data.comparison]} (düz)</span></p>}
  </section>;
}
