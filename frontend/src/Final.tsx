import {useEffect, useRef, useState} from 'react';
import type {KeyboardEvent, PointerEvent} from 'react';
import './final.css';

const API = '/api/final/v1';
const WEIGHTED = 'weighted_unmet_volume_m3';
const METRICS = [
  [WEIGHTED, 'Ağırlıklı hizmet açığı', 'ağırlıklı m³', 6],
  ['unmet_demand_volume_m3', 'Ağırlıksız hizmet açığı', 'm³', 6],
  ['critical_low_pressure_node_hours', 'Kritik düşük basınç', 'düğüm·saat', 1],
  ['repair_completion_hour', 'Son onarım', 'saat', 0],
] as const;
const NAMES: Record<string, string> = {fifo:'Bildirim sırası (FIFO)', greedy:'Tekli etki/süre',
  proposal:'ŞebekeKalkan v2', s02_b6:'ŞebekeKalkan S02-B6', s02_b12:'ŞebekeKalkan S02-B12', oracle:'Tam sayım'};
const GROUPS: Record<string, string> = {internal_holdout:'Net2 · Ayrılmış iç değerlendirme',
  external_holdout:'Skeletonize · Dış değerlendirme', sprint01:'Sprint 01 · Net2 ana deney',
  historical:'Tarihsel deney', dev:'Net2 · Geliştirme'};
const TITLES: Record<string, string> = {Net2_G4_C1:'Dört arızada daha az hizmet açığı', Net2_S3_C1:'Bildirim sırasının etkisi',
  Skeletonize_G1_C1:'Başka ağdaki eşitlik', Net2_S1_C3:'Üç ekipte eşitlik', Net2_S1_C2:'Aynı açık, daha erken son onarım',
  Net1_A3_C1:'Net1 tarihsel örneği', Net3_A1_C1:'Net3 tarihsel örneği'};
type Point = [number, number];
type Assignment = {pipe_id:string; crew:number; starts_at_h:number; ends_at_h:number};
type Method = {order:string[]|null; metrics:Record<string, number>; assignments:Assignment[]|null;
  deficit:Point[]|null; physics:Record<string, unknown>};
type Card = {case_id:string; group:string; status:string; baseline?:string; comparison?:string;
  metrics?:{baseline:number;comparison:number}};
type Detail = {case_id:string; network:string; group:string; baseline:string; comparison:string; crews:number;
  failures:string[]; horizon_hours:number; failure_start_hour:number; methods:Record<string, Method>;
  diagram:{pipes:Record<string, Point[]>; other_links:Point[][]; nodes:Record<string, Point>};
  evidence:{record_id:string; method_version:string; source_stage:string; network_sha256:string;
    scenario_sha256:string; record_sha256:string; record_path:string; model_path:string; code_sha256?:string;
    protocol_sha256?:string; solver?:string; decision_sha256?:string; record_selector?:unknown}};
type Counts = Record<string, number>;
type Research = {groups:Record<string, Counts>; total:Counts; source:string; source_sha256:string;
  gap:{method:string;weighted_unmet_volume_m3:string}[];
  losses:{case:string;metric:string;baseline:string;proposal:string;baseline_value:number;proposal_value:number}[]};
const number = (value:number, digits=6) => new Intl.NumberFormat('tr-TR',
  {minimumFractionDigits:digits, maximumFractionDigits:digits}).format(value);
const change = (a:number, b:number) => a ? 100*(a-b)/a : null;
const order = (ids:string[]|null) => ids?.join(' → ') || 'Sıra detayı mevcut değil';
const endpoint = (id:string) => '/cases/' + encodeURIComponent(id);
async function get<T>(path:string, signal?:AbortSignal):Promise<T> {
  const res = await fetch(API+path, {signal,cache:'no-store'});
  if (!res.ok) throw new Error('Kaynak doğrulanamadı.');
  return res.json();
}

function Download({path, name, json=false, unavailable}: {path:string;name:string;json?:boolean;unavailable?:()=>void}) {
  const [error,setError] = useState('');
  const [pending,setPending] = useState(false);
  async function save(ext:string) {
    setPending(true);
    setError('');
    try {
      const r = await fetch(API+path+(ext==='json'?'/evidence':'/chart.svg'), {cache:'no-store'});
      if (!r.ok) {
        unavailable?.();
        throw new Error();
      }
      let blob = await r.blob();
      if (ext==='png') {
        const url = URL.createObjectURL(blob);
        try {
          const img = new Image();
          img.src = url;
          await img.decode();
          const cv = document.createElement('canvas');
          cv.width = img.width;
          cv.height = img.height;
          cv.getContext('2d')!.drawImage(img,0,0);
          blob = await new Promise<Blob>((resolve,reject) => cv.toBlob(b => b?resolve(b):reject(new Error()),'image/png'));
        } finally { URL.revokeObjectURL(url); }
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name+'.'+ext;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch { setError('Çıktı alınamadı. Kaynağı yeniden kontrol edin.'); }
    finally { setPending(false); }
  }
  return <div className="fd-actions">
    <button disabled={pending} onClick={() => void save('svg')}>SVG indir</button>
    <button disabled={pending} onClick={() => void save('png')}>PNG indir</button>
    {json && <button disabled={pending} onClick={() => void save('json')}>Kanıt JSON indir</button>}
    {error&&<span role="alert">{error}</span>}
  </div>;
}

function Network({data, method}:{data:Detail;method:Method}) {
  const {pipes,other_links,nodes}=data.diagram;
  const coords=Object.values(nodes);
  const minX=Math.min(...coords.map(x=>x[0])), minY=Math.min(...coords.map(x=>x[1]));
  const w=Math.max(...coords.map(x=>x[0]))-minX || 1, h=Math.max(...coords.map(x=>x[1]))-minY || 1;
  const pad=Math.max(w,h)*.07;
  const [camera,setCamera]=useState({x:0,y:0,z:1});
  const drag=useRef<{x:number;y:number}|null>(null);
  const bw=(w+2*pad)/camera.z,bh=(h+2*pad)/camera.z;
  const origin=[minX+(w-bw)/2+camera.x,minY+(h-bh)/2+camera.y];
  const points=(p:Point[])=>p.map(pair=>pair.join(',')).join(' ');
  const zoom=(factor:number)=>setCamera(c=>({...c,z:Math.max(.7,Math.min(6,c.z*factor))}));
  const move=(x:number,y:number)=>setCamera(c=>({...c,x:c.x+x,y:c.y+y}));
  function key(e:KeyboardEvent<SVGSVGElement>) {
    const vector:Record<string,Point>={ArrowLeft:[-bw/10,0],ArrowRight:[bw/10,0],ArrowUp:[0,-bh/10],ArrowDown:[0,bh/10]};
    if (vector[e.key]) { e.preventDefault(); move(...vector[e.key]); }
    if (e.key==='+' || e.key==='-') { e.preventDefault(); zoom(e.key==='+'?1.3:1/1.3); }
  }
  function pan(e:PointerEvent<SVGSVGElement>) {
    if (!drag.current) return;
    const scale=Math.max(bw/e.currentTarget.clientWidth,bh/e.currentTarget.clientHeight);
    move((drag.current.x-e.clientX)*scale,(drag.current.y-e.clientY)*scale);
    drag.current={x:e.clientX,y:e.clientY};
  }
  const selected = method.order || data.failures;
  return <section className="fd-panel fd-network">
    <div className="fd-panel-head"><div><h3>Şebeke şeması</h3><p>{data.network} · INP çizim koordinatları · {data.crews} ekip</p></div>
      {!!coords.length&&<div className="fd-actions fd-zoom"><button aria-label="Uzaklaştır" onClick={()=>zoom(1/1.3)}>−</button>
        <button aria-label="Yakınlaştır" onClick={()=>zoom(1.3)}>+</button>
        <button onClick={()=>setCamera({x:0,y:0,z:1})}>Sıfırla</button></div>}
    </div>
    {coords.length ? <svg className="fd-map" tabIndex={0} aria-label={data.network+' şeması. Ok tuşlarıyla kaydırın.'} role="img"
      viewBox={origin.concat(bw,bh).join(' ')} onKeyDown={key}
      onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);drag.current={x:e.clientX,y:e.clientY};}}
      onPointerMove={pan} onLostPointerCapture={()=>{drag.current=null;}}>
      <g fill="none" stroke="#9baeb7" strokeWidth="1.25">
        {Object.entries(pipes).map(([id,p])=><polyline key={id} points={points(p)} vectorEffect="non-scaling-stroke"/>)}
        {other_links.map((p,i)=><polyline key={i} points={points(p)} strokeDasharray="3 2" vectorEffect="non-scaling-stroke"/>)}
      </g>
      <g fill="#7596a3">{coords.map(([x,y],i)=><circle key={i} cx={x} cy={y} r={Math.max(bw,bh)/240}/>)}</g>
      {selected.map(id=>pipes[id]&&<polyline key={id} points={points(pipes[id])} fill="none" stroke="#c05232"
        strokeWidth="4" strokeLinecap="round" vectorEffect="non-scaling-stroke"><title>Boru {id}</title></polyline>)}
      <g fill="#fff" stroke="#c05232">{selected.map((id,i)=>{
        if (!pipes[id]) return null;
        const p=pipes[id], a=p[Math.floor((p.length-1)/2)], b=p[Math.ceil((p.length-1)/2)];
        const x=(a[0]+b[0])/2, y=(a[1]+b[1])/2, s=Math.max(bw,bh)/54;
        return <g key={id}><circle cx={x} cy={y} r={s} strokeWidth="1.5" vectorEffect="non-scaling-stroke"/>
          <text x={x} y={y+s*.33} textAnchor="middle" stroke="none" fill="#853217" fontSize={s*1.16}>{method.order?i+1:'•'}</text></g>;
      })}</g>
    </svg>:<p>Kaynakta çizim koordinatı bulunamadı.</p>}
    <p className="fd-order"><span className="fd-failure-key"/> Arızalı borular · {method.order?order(method.order):data.failures.join(', ')}</p>
    <p>Şema konum ve ulaşım güzergâhı bilgisi içermez.</p>
    {selected.some(id=>!pipes[id])&&<p>Çizim koordinatı eksik borular {selected.filter(id=>!pipes[id]).join(', ')}.</p>}
  </section>;
}

function Timeline({data, active}:{data:Detail;active:string}) {
  const methods=Object.entries(data.methods);
  if (!methods.some(([,m])=>m.assignments)) return <section className="fd-panel"><h3>Onarım zaman çizelgesi</h3><p>Çizelge detayı mevcut değil.</p></section>;
  const end=data.horizon_hours;
  return <section className="fd-panel fd-timeline"><h3>Onarım zaman çizelgesi</h3>
    <p>Arızaların başlangıcı {number(data.failure_start_hour,0)}. saat · Simülasyon ufku {number(end,0)} saat</p>
    {methods.map(([id,m])=><div key={id} className={'fd-gantt-method'+(active===id?' selected':'')}>
      <div className="fd-gantt-title"><strong>{NAMES[id]}</strong><span>Bitiş {number(m.metrics.repair_completion_hour,0)}. saat</span></div>
      {Array.from({length:data.crews},(_,i)=>i+1).map(crew=><div className="fd-lane" key={crew}>
        <span>Ekip {crew}</span><div className="fd-track">
          {m.assignments?.filter(a=>a.crew===crew).map(a=><span key={a.pipe_id}
            className="fd-job" title={`Boru ${a.pipe_id}, ekip ${crew}, ${a.starts_at_h}–${a.ends_at_h}. saat`}
            aria-label={`Boru ${a.pipe_id}, ${a.starts_at_h}–${a.ends_at_h}. saat`}
            style={{left:`${a.starts_at_h/end*100}%`,width:`${(a.ends_at_h-a.starts_at_h)/end*100}%`}}>{a.pipe_id}</span>)}
        </div>
      </div>)}
    </div>)}
    <div className="fd-ticks" aria-hidden="true">{[0,.25,.5,.75,1].map(t=><span key={t}>{number(t*end,0)} sa.</span>)}</div>
    <details className="fd-source"><summary>Boru, ekip ve saatler</summary>
      {methods.map(([id,m])=><p key={id}><strong>{NAMES[id]}</strong> · {m.assignments?.map(a=>`${a.pipe_id} (ekip ${a.crew}, ${a.starts_at_h}–${a.ends_at_h}. saat)`).join(' · ')}</p>)}
    </details>
  </section>;
}

function Service({data, active}:{data:Detail;active:string}) {
  const series=data.methods[active].deficit;
  if (!series) return <section className="fd-panel"><h3>Zamana bağlı hizmet</h3><p>Bu kayıtta ham zaman serisi bulunmuyor. Ölçülen toplam hizmet açığı karşılaştırma panelinde.</p></section>;
  const max=Math.max(...series.map(p=>p[1])) || 1;
  const x=(v:number)=>54+v/data.horizon_hours*650;
  const y=(v:number)=>174-v/max*141;
  const path=series.map(([t,v],i)=>i?'H'+x(t)+'V'+y(v):'M'+x(t)+' '+y(v)).join(' ');
  return <section className="fd-panel"><h3>Zamana bağlı hizmet açığı</h3>
    <p>{NAMES[active]} · Pozitif müşteri talebinden karşılanamayan toplam debi (L/s)</p>
    <svg className="fd-series" viewBox="0 0 724 218" role="img" aria-label="Saatlere göre karşılanamayan toplam talep debisi">
      {[0,.5,1].map(f=><g key={f}><path d={`M54 ${y(max*f)} H704`} stroke="#d7e0e7"/>
        <text x="47" y={y(max*f)+4} textAnchor="end">{number(max*f,1)}</text></g>)}
      {[0,.25,.5,.75,1].map(f=><text key={f} x={x(f*data.horizon_hours)} y="198" textAnchor="middle">{number(f*data.horizon_hours,0)} sa.</text>)}
      <path d={path} fill="none" stroke="#007b70" strokeWidth="2.4" vectorEffect="non-scaling-stroke"/>
    </svg>
    <p>Kaynak {data.case_id} · {data.evidence.source_stage} · Örnekler arasındaki yatay çizgi rapor adımını gösterir.</p>
  </section>;
}

function Comparisons({data, invalidate}:{data:Detail;invalidate:()=>void}) {
  return <section className="fd-panel" id="comparison"><div className="fd-panel-head">
    <div><h3>Planların karşılaştırması</h3><p>Küçük değer daha iyi · Yüzde değişim {NAMES[data.baseline]} referansına göre</p></div>
    <Download path={endpoint(data.case_id)} name={data.case_id} json unavailable={invalidate}/></div>
    <div className="fd-metrics">{METRICS.map(([key,label,unit,digits])=>{
      const a=data.methods[data.baseline].metrics[key], b=data.methods[data.comparison].metrics[key], pct=change(a,b);
      const scale=Math.max(...Object.values(data.methods).map(m=>m.metrics[key])) || 1;
      return <div className="fd-metric" key={key}><h4>{label} <small>({unit})</small></h4>
        {pct!==null&&<p className={a>b?'fd-positive':a<b?'fd-negative':''}>
          {pct===0?'Eşit':`% ${number(Math.abs(pct),2)} ${pct>0?'daha düşük':'daha yüksek'}`}
        </p>}
        {Object.entries(data.methods).map(([id,m])=><div className={'fd-measure'+(id===data.comparison?' proposal':'')} key={id}>
          <span>{NAMES[id]}</span><strong>{number(m.metrics[key],digits)}</strong>
          <div className="fd-bar" aria-hidden="true"><span style={{width:`${100*m.metrics[key]/scale}%`}}/></div>
        </div>)}
      </div>;
    })}</div>
    <p>Kaynak {data.case_id} · {data.evidence.source_stage} · Kayıt {data.evidence.record_id}</p>
  </section>;
}

function summary(data:Detail) {
  const a=data.methods[data.baseline].metrics[WEIGHTED], b=data.methods[data.comparison].metrics[WEIGHTED];
  return {a,b,difference:a-b,percent:change(a,b),vsStrong:data.methods.greedy.metrics[WEIGHTED]-b};
}

function Case({data, invalidate}:{data:Detail;invalidate:()=>void}) {
  const [active,setActive]=useState(data.comparison);
  const proof=data.evidence, numbers=summary(data);
  return <>
    <section className="fd-panel fd-story" aria-labelledby="active-case">
      <div className="fd-panel-head"><div><p className="fd-eyebrow">Kayıtlı ve doğrulanmış sonuç</p>
        <h2 id="active-case" tabIndex={-1}>{TITLES[data.case_id]}</h2>
        <p>{GROUPS[data.group]} · {data.case_id} · {data.failures.length} arıza · {data.crews} ekip</p></div>
        <div className="fd-big">
          <span>{numbers.percent===null?'Ağırlıklı fark':numbers.percent===0?'Ağırlıklı açık eşit':'Ağırlıklı hizmet açığı'}</span>
          <strong>{numbers.percent===null?number(numbers.difference):numbers.percent===0?number(numbers.b):`% ${number(Math.abs(numbers.percent),2)}`}</strong>
          <span>{numbers.percent!==null&&numbers.percent!==0?`${numbers.percent>0?'Daha düşük':'Daha yüksek'} · ${number(Math.abs(numbers.difference))} ağırlıklı m³ fark`:'ağırlıklı m³'}</span>
        </div>
      </div>
      <p><strong>{NAMES[data.baseline]}</strong> {number(numbers.a)} → <strong>{NAMES[data.comparison]}</strong> {number(numbers.b)} ağırlıklı m³.</p>
      {data.case_id==='Net2_S3_C1'&&numbers.vsStrong===0&&<p className="fd-note"><strong>Güçlü tekli etkiye karşı kazanç sıfır.</strong> Tekli etki/süre de {number(numbers.b)} ağırlıklı m³ buldu.</p>}
      {data.case_id==='Skeletonize_G1_C1'&&<p className="fd-note">Tekli etki/süre ve S02-B6 aynı sırayı verdi. Dış ağdaki tüm koşulların dağılımı araştırma tablosunda.</p>}
      <div className="fd-actions"><label htmlFor="fd-method">Şema ve hizmet grafiği</label>
        <select id="fd-method" value={active} onChange={e=>setActive(e.target.value)}>
          {Object.keys(data.methods).map(key=><option key={key} value={key}>{NAMES[key]}</option>)}
        </select>
        <a href="#proof">Kaynağı incele</a>
      </div>
    </section>
    <div className="fd-pair"><Network data={data} method={data.methods[active]}/><Timeline data={data} active={active}/></div>
    <Comparisons data={data} invalidate={invalidate}/>
    <Service data={data} active={active}/>
    <section className="fd-panel" id="proof"><h3>Bu sıra nasıl seçildi?</h3>
      <p>Ağırlıklı hizmet açığı, karşılanamayan talebi önemli düğümlere daha yüksek katsayı vererek ölçer. Kritik düşük basınç düğüm·saati, önemli düğümlerin eşik altında kaldığı sürelerin toplamıdır. Tekli etki/süre, her borunun ayrı etkisini ve onarım süresini kullanır.</p>
      <p>Kapsam, test ağı simülasyonu. Sonuçlar sahada ölçülen su miktarını temsil etmez. Onarım bitişi ile hizmetin geri gelişi farklı ölçümlerdir.</p>
      <details className="fd-source"><summary>Fizik kapıları, kayıt kimliği ve SHA-256</summary>
        {data.methods.s02_b6&&<p>S02-B6, {String(data.methods.s02_b6.physics.budget)} aday bütçesine bildirim sırasını ve tekli etki/süreyi zorunlu alır. Bu yapı birincil ölçütte güçlü referansa göre kayıp gözlenmemesini açıklar. Basınca bağlı talep, mevcut basınçla teslim edilebilen debiyi hesaplar. Tam sayım dört arızanın 24 beklemesiz öncelik sırasını deneyen araştırma karşılaştırmasıdır.</p>}
        <dl className="fd-evidence">
          {Object.entries({'Durum':'Fizik kapıları geçti','Kayıt':proof.record_id,'Yöntem':proof.method_version,
            'Çözücü':proof.solver,'Kayıt dosyası':proof.record_path,'Model dosyası':proof.model_path,
            'Kayıt SHA-256':proof.record_sha256,'Ağ SHA-256':proof.network_sha256,'Senaryo SHA-256':proof.scenario_sha256,
            'Kod SHA-256':proof.code_sha256,'Protokol SHA-256':proof.protocol_sha256,'Karar SHA-256':proof.decision_sha256}).filter(([,value])=>value)
            .map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
        </dl>
        {Object.entries(data.methods).map(([id,m])=><details key={id}><summary>{NAMES[id]} · Fizik kaydı</summary><pre>{JSON.stringify(m.physics,null,2)}</pre></details>)}
      </details>
    </section>
  </>;
}

function ResearchPanel({data}:{data:Research}) {
  const counts=(v:Counts)=>`${v.WIN||0} kazanım / ${v.TIE||0} eşitlik / ${v.LOSS||0} kayıp`;
  const total=(v:Counts)=>Object.values(v).reduce((n,m)=>n+m,0);
  const gap=data.gap.find(x=>x.method==='s02_b6'), best=data.gap.find(x=>x.method==='oracle');
  return <section className="fd-panel" id="research"><div className="fd-panel-head"><div>
    <h2>Araştırma kapsamı</h2><p>S02-B6 ve tekli etki/süre · Ağırlıklı hizmet açığı</p></div>
    <Download path="/research" name="Sprint02-karsilastirma"/></div>
    <div className="fd-group-grid">{[...Object.entries(data.groups),['total',data.total] as const].map(([key,vals])=>
      <article key={key}><h3>{GROUPS[key]||'Toplam'} · {total(vals)} koşul</h3><p>{counts(vals)}</p>
        <div className="fd-distribution" aria-hidden="true">{['WIN','TIE','LOSS'].map(mark=>
          <span key={mark} className={mark} style={{flexBasis:`${(vals[mark]||0)/total(data.total)*100}%`}}/>)}</div></article>)}</div>
    <p>Dış ağdaki {total(data.groups.external_holdout)} koşulun tamamı birincil ölçütte eşit. Başka şebekelerde genel üstünlük sonucu çıkarılamaz.</p>
    <details className="fd-source"><summary>Kaçırılan ve kötüleşen sonuçlar</summary>
      {gap&&best&&<p>Net2_G1_C1 · S02-B6 {number(Number(gap.weighted_unmet_volume_m3))}, tam sayım {number(Number(best.weighted_unmet_volume_m3))} ağırlıklı m³. Fark {number(Number(gap.weighted_unmet_volume_m3)-Number(best.weighted_unmet_volume_m3))} ağırlıklı m³.</p>}
      <ul>{data.losses.map(row=>{
        const [,label,unit,digits]=METRICS.find(x=>x[0]===row.metric)!;
        return <li key={row.case+row.metric}>{row.case} · {NAMES[row.baseline]} → {NAMES[row.proposal]} · {label} {number(row.baseline_value,digits)} → {number(row.proposal_value,digits)} {unit}</li>;
      })}</ul>
      <p>Kaynak {data.source}</p><code>{data.source_sha256}</code>
    </details>
  </section>;
}

type LiveJob = {
  job_id:string;case_id:string;status:string;message:string;timeout_seconds:number;solver:string;
  method_version:string;worker_exit_code?:number|null;elapsed_seconds?:number;failure_code?:string;
  input_sha256:string;scenario_sha256:string;source_sha256:string;adapter_sha256:string;
  protocol_sha256:string;network_sha256:string;
  result?:{wntr_calls:number;trial_count:number;physical_pass:boolean;methods:Record<string,
    {order:string[];metrics:Record<string,number>;physical:Record<string,unknown>}>};
};
type LiveChoices = {scenarios:{case_id:string;crews:number}[];diagnostic:boolean};
const liveLabels:Record<string,string> = {queued:'Sırada',running:'Hesaplanıyor',completed:'Tamamlandı',
  failed:'Başarısız',timeout:'Zaman aşımı'};

function Live() {
  const [choices,setChoices]=useState<LiveChoices|null>(null);
  const [selection,setSelection]=useState('Net2_G4_C1');
  const [job,setJob]=useState<LiveJob|null>(null);
  const [problem,setProblem]=useState('');
  const [submitting,setSubmitting]=useState(false);
  const id=job?.job_id;
  const waiting=job?.status==='queued'||job?.status==='running';
  useEffect(()=>{
    const c=new AbortController();
    get<LiveChoices>('/live/scenarios',c.signal).then(setChoices).catch(()=>{
      if(!c.signal.aborted)setProblem('Kilitli canlı senaryolar doğrulanamadı.');
    });
    return ()=>c.abort();
  },[]);
  useEffect(()=>{
    if(!id || !waiting) return;
    const c=new AbortController();
    let timer:number;
    async function poll() {
      try {
        const next=await get<LiveJob>('/live/jobs/'+id,c.signal);
        if(c.signal.aborted) return;
        setProblem('');setJob(next);
        if(next.status==='queued'||next.status==='running')timer=window.setTimeout(poll,850);
      } catch {
        if(c.signal.aborted) return;
        setProblem('İş durumu okunamadı. Yerel bağlantı tekrar denenecek.');
        timer=window.setTimeout(poll,1800);
      }
    }
    timer=window.setTimeout(poll,350);
    return ()=>{c.abort();window.clearTimeout(timer);};
  },[id,waiting]);
  async function start() {
    setSubmitting(true);setProblem('');setJob(null);
    try {
      const r=await fetch(API+'/live/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({case_id:selection})});
      const value=await r.json();
      if(!r.ok) throw new Error(value.message||'Canlı iş başlatılamadı.');
      setJob(value);
    } catch(e){setProblem(e instanceof Error?e.message:'Canlı iş başlatılamadı.');}
    finally{setSubmitting(false);}
  }
  return <section id="four-live" className="fd-panel">
    <div><h2>Dört arıza canlı hesap</h2>
      <p>Ön kayıtlı Net2 ve Skeletonize senaryolarında yeni WNTR işi. Jüri gösterimi için kayıtlı vakalar hazır.</p></div>
    {choices?.diagnostic&&<p className="fd-note">Çözücü hata denetimi etkin. Bu oturumda yakınsama sınırı düşürüldü.</p>}
    {choices&&<div className="fd-actions">
      <label htmlFor="live-case">Kilitli senaryo</label>
      <select id="live-case" value={selection} disabled={submitting||waiting} onChange={e=>{setSelection(e.target.value);setJob(null);setProblem('');}}>
        {choices.scenarios.map(s=><option key={s.case_id} value={s.case_id}>{s.case_id} · {s.crews} ekip</option>)}
      </select>
      <button className="fd-primary" disabled={submitting||waiting} onClick={()=>void start()}>Canlı hesapla</button>
    </div>}
    {problem&&<p role="alert">{problem}</p>}
    {job&&<div className="fd-live-job">
      <p role="status"><strong>{liveLabels[job.status]}</strong> · {job.message}</p>
      <p>Canlı iş {job.job_id} · {job.case_id} · {job.timeout_seconds} saniye sınırı</p>
      {job.failure_code&&<p>Motor hata kodu {job.failure_code}</p>}
      {job.result?.physical_pass&&job.status==='completed'&&<>
        <p>Fizik kapıları geçti. {job.result.wntr_calls} çözücü çağrısı, {job.result.trial_count} fizik koşusu.</p>
        <div className="fd-metrics">{Object.entries(job.result.methods).map(([method,result])=>
          <article className="fd-metric" key={method}><h3>{NAMES[method]}</h3><p>{order(result.order)}</p>
            <dl className="fd-evidence">{METRICS.map(([key,label,unit,digits])=><div key={key}>
              <dt>{label}</dt><dd>{number(result.metrics[key],digits)} {unit}</dd></div>)}</dl>
            <details className="fd-source"><summary>Fizik kaydı</summary><pre>{JSON.stringify(result.physical,null,2)}</pre></details>
          </article>)}</div>
        <div className="fd-actions">{['csv','json','pdf'].map(ext=>
          <a key={ext} href={`${API}/live/jobs/${job.job_id}/export/${ext}`} download>{ext.toUpperCase()} indir</a>)}</div>
      </>}
      <details className="fd-source"><summary>Canlı hesap kimliği ve kaynak</summary>
        <dl className="fd-evidence">{Object.entries({'Çözücü':job.solver,'Yöntem':job.method_version,'Girdi SHA-256':job.input_sha256,
          'Ağ SHA-256':job.network_sha256,'Senaryo SHA-256':job.scenario_sha256,'Kaynak SHA-256':job.source_sha256,
          'İşçi kodu SHA-256':job.adapter_sha256,'Protokol SHA-256':job.protocol_sha256,'İşçi çıkış kodu':job.worker_exit_code,
          'Geçen süre':job.elapsed_seconds===undefined?null:number(job.elapsed_seconds,2)+' saniye'}).filter(([,v])=>v!=null)
          .map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
      </details>
    </div>}
  </section>;
}

export default function Final() {
  const [cards,setCards]=useState<Card[]|null>(null);
  const [data,setData]=useState<Detail|null>(null);
  const [science,setScience]=useState<Research|null>(null);
  const [failed,setFailed]=useState(false);
  const [researchFailed,setResearchFailed]=useState(false);
  const [selection,setSelection]=useState<{id:string;sequence:number}|null>(null);
  const [present,setPresent]=useState(false);
  const presentation=useRef<HTMLDivElement>(null);
  const restore=useRef<HTMLElement|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    get<Card[]>('/catalog',controller.signal).then(setCards).catch(()=>{if(!controller.signal.aborted)setCards([]);});
    get<Research>('/research',controller.signal).then(setScience).catch(()=>{if(!controller.signal.aborted)setResearchFailed(true);});
    return ()=>controller.abort();
  },[]);
  useEffect(()=>{
    if(!selection) return;
    const controller=new AbortController();
    get<Detail>(endpoint(selection.id),controller.signal).then(value=>{
      setData(value);
      requestAnimationFrame(()=>document.getElementById('active-case')?.focus());
    }).catch(()=>{
      if(controller.signal.aborted) return;
      setFailed(true);
      setCards(old=>old?.map(card=>card.case_id===selection.id?
        {case_id:card.case_id,group:card.group,status:'unverified'}:card)||null);
    });
    return ()=>controller.abort();
  },[selection]);
  const choose=(id:string)=>{
    setData(null);setFailed(false);
    setSelection(old=>({id,sequence:(old?.sequence||0)+1}));
  };
  function invalidate() {
    if(!selection) return;
    const id=selection.id;
    setData(null);setFailed(true);
    setCards(old=>old?.map(card=>card.case_id===id?{case_id:id,group:card.group,status:'unverified'}:card)||null);
  }
  function exit() {
    setPresent(false);
    if(document.fullscreenElement) void document.exitFullscreen().catch(()=>{});
    restore.current?.focus();
  }
  async function start() {
    restore.current=document.activeElement as HTMLElement;
    setPresent(true);
    if(!selection||failed) choose('Net2_G4_C1');
    requestAnimationFrame(()=>{
      presentation.current?.querySelector('button')?.focus();
      void presentation.current?.requestFullscreen?.().catch(()=>{});
    });
  }
  useEffect(()=>{
    if(!present) return;
    function full(){if(!document.fullscreenElement){setPresent(false);restore.current?.focus();}}
    function esc(e:globalThis.KeyboardEvent){
      if(e.key==='Escape'){
        setPresent(false);
        if(document.fullscreenElement) void document.exitFullscreen().catch(()=>{});
        requestAnimationFrame(()=>restore.current?.focus());
      }
    }
    document.addEventListener('fullscreenchange',full);
    document.addEventListener('keydown',esc);
    return ()=>{document.removeEventListener('fullscreenchange',full);document.removeEventListener('keydown',esc);};
  },[present]);
  const caseBody=data?<Case key={data.case_id} data={data} invalidate={invalidate}/>:
      failed?<p className="fd-panel" role="alert">Kaynak doğrulanamadı. Sayılar ve dışa aktarma kapatıldı.</p>:
      selection?<p className="fd-panel" role="status">Kayıt okunuyor.</p>:null;
  return <div className="fd">
    <header className="masthead fd-header" inert={present}><a className="skip" href="#fd-main">İçeriğe geç</a>
      <a className="brand" href="/final" aria-label="ŞebekeKalkan final gösterimi"><svg viewBox="0 0 32 32" aria-hidden="true">
        <path d="M16 2 29 8v9c0 7-8 11-13 14C11 28 3 24 3 17V8Z M8 17h7l4-7 5 10" fill="none" stroke="currentColor" strokeWidth="2"/>
      </svg><strong>ŞebekeKalkan</strong></a>
      <nav aria-label="Gösterim modları"><a href="#cases">Kayıtlı vakalar</a><a href="#four-live">Dört arıza canlı</a><a href="/">Net3 · Üç arıza canlı</a></nav>
    </header>
    <main className="fd-main" id="fd-main" inert={present}>
      <section className="fd-hero"><div><p className="fd-eyebrow">Final gösterimi · Fizik tabanlı karar desteği</p>
        <h1>Önce hangi boru onarılmalı?</h1>
        <p>Aynı arızaları farklı sıralarda onarmanın su hizmetine etkisini karşılaştırın.</p>
        <div className="fd-actions"><button className="fd-primary" onClick={()=>void start()}>Gösterimi başlat</button>
          <a href="#research">Araştırma kanıtı</a></div></div>
        <ol className="fd-flow"><li>Arızaları belirle</li><li>Sıraları hesapla</li><li>Su hizmetine etkisini karşılaştır</li></ol>
      </section>
      <section id="cases" aria-labelledby="fd-cases"><div className="fd-section-head"><h2 id="fd-cases">Kayıtlı ve doğrulanmış sonuç</h2><p>Seçili test ağı vakaları</p></div>
        {cards===null?<p role="status">Kayıtlar okunuyor.</p>:!cards.length?<p role="alert">Kayıt kataloğuna ulaşılamadı.</p>:
          <div className="fd-cards">{cards.map((card,i)=><article key={card.case_id} className={(i<3?'featured ':'')+(selection?.id===card.case_id?'active':'')}>
            <p className="fd-eyebrow">{GROUPS[card.group]}</p>
            <h3>{TITLES[card.case_id]}</h3><p>{card.case_id}</p>
            {card.metrics?<><div className="fd-card-value">{number(card.metrics.comparison)} <small>ağırlıklı m³</small></div>
              <p>{NAMES[card.baseline!]} {number(card.metrics.baseline)}</p>
              <button aria-label={`Vakayı aç ${card.case_id}`} onClick={()=>choose(card.case_id)}>Vakayı aç</button></>:
              <p role="status">Kaynak doğrulanamadı.</p>}
          </article>)}</div>}
      </section>
      {!present&&caseBody}
      {science&&<ResearchPanel data={science}/>}
      {!science&&<section id="research" className="fd-panel"><h2>Araştırma kapsamı</h2>
        <p role={researchFailed?'alert':'status'}>{researchFailed?'Araştırma kaynağı doğrulanamadı.':'Araştırma kaydı okunuyor.'}</p></section>}
      <Live/>
    </main>
    {present&&<div className="fd-presentation" ref={presentation} role="dialog" aria-modal="true" aria-label="Jüri sunumu">
      <div className="fd-present-bar"><strong>ŞebekeKalkan · Jüri sunumu</strong>
        <div className="fd-actions">
          {cards?.slice(0,3).map((c,i)=>c.status==='verified'&&<button key={c.case_id} aria-pressed={selection?.id===c.case_id}
            onClick={()=>choose(c.case_id)}>{['Ana Net2','Bildirim sırası','Dış ağ'][i]}</button>)}
          <button onClick={exit}>Sunumdan çık (Esc)</button>
        </div></div>
      <div className="fd-present-body">{caseBody}</div>
    </div>}
  </div>;
}
