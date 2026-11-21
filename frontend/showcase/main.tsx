import {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import NetworkStage, {BANDS} from '../src/final-v4/NetworkStage';
import type {PipeMark} from '../src/final-v4/NetworkStage';
import type {Diagram, Point, Trace} from '../src/final-v4/domain';
import proof from '../../data/demo/kanit.json';
import './showcase.css';

const {net,mu,study}=proof;
const names={greedy:'Güçlü referans',s02_b6:'ŞebekeKalkan B6'};
type Plan=keyof typeof names;
const plans=['greedy','s02_b6'] as const;
const num=(v:number,d=2)=>v.toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d});
const clock=(minutes:number)=>[Math.floor(minutes/60),minutes%60].map(v=>String(v).padStart(2,'0')).join('.');
const timeline=net.traces.greedy.minutes;
const point=([x,y]:number[]):Point=>[x,y];
const diagram:Diagram={
  nodes:Object.fromEntries(Object.entries(net.diagram.nodes).map(([id,p])=>[id,point(p)])),
  pipes:Object.fromEntries(Object.entries(net.diagram.pipes).map(([id,p])=>[id,p.map(point)])),
  other_links:(net.diagram.other_links as number[][][]).map(p=>p.map(point)),
};
const offline=window.location.protocol==='file:';
const apiBase=import.meta.env.VITE_API_BASE_URL?.replace(/\/$/,'')??'';
const local=/^(127\.0\.0\.1|localhost|\[::1\])$/.test(window.location.hostname);
const route=window.location.pathname;
const researchPage=route!=='/demo/'&&route.endsWith('/demo/')?'../research/arastirma.html':'./research/arastirma.html';

function download(name:string,content:string,type:string){
  const url=URL.createObjectURL(new Blob([content],{type}));
  const link=document.createElement('a');
  link.href=url;
  link.download=name;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function Logo(){
  return <svg viewBox="0 0 36 36" aria-hidden="true"><path d="M18 2.5 32 8v10c0 7-6 12-14 15.5C10 30 4 25 4 18V8Z"/><path d="m9 19 6-5 6 6 6-7"/><circle cx="9" cy="19" r="1.5"/><circle cx="27" cy="13" r="1.5"/></svg>;
}

function Service(){
  const [mode,setMode]=useState<Plan>('s02_b6');
  const [step,setStep]=useState(timeline.indexOf(480));
  const [playing,setPlaying]=useState(false);
  const [live,setLive]=useState<'checking'|'local'|'remote'|'unavailable'>(local||apiBase?'checking':'unavailable');
  const trace:Trace=net.traces[mode];
  const minute=timeline[step];
  const active=net.methods[mode];
  const pressures=Object.fromEntries(trace.node_ids.map((id,i)=>[id,trace.pressure_m[step][i]]));
  const marks=Object.fromEntries(active.assignments.map((repair,i)=>{
    const open=trace.link_status[step][trace.pipe_ids.indexOf(repair.pipe_id)]!==0;
    const kind=minute<120?'pending':open?'repaired':minute>=repair.starts_at_h*60?'work':'fault';
    return [repair.pipe_id,{kind,label:repair.pipe_id,description:`Öncelik ${i+1}`} satisfies PipeMark];
  }));
  useEffect(()=>{
    if(!playing)return;
    const timer=window.setInterval(()=>{
      setStep(i=>Math.min(i+1,timeline.length-1));
    },280);
    return ()=>window.clearInterval(timer);
  },[playing]);
  useEffect(()=>{
    if(!local&&!apiBase)return;
    const controller=new AbortController();
    const timeout=window.setTimeout(()=>controller.abort(),3500);
    fetch(apiBase+'/healthz',{signal:controller.signal,cache:'no-store'})
      .then(r=>r.ok?r.json():Promise.reject())
      .then(data=>setLive(data.solver==='WNTR'&&data.live==='local'&&local?'local':
        data.solver==='WNTR'&&data.live==='isolated'&&apiBase?'remote':'unavailable'))
      .catch(()=>setLive('unavailable')).finally(()=>clearTimeout(timeout));
    return ()=>{controller.abort();clearTimeout(timeout);};
  },[]);
  useEffect(()=>{if(step===timeline.length-1&&playing)setPlaying(false);},[step,playing]);
  function move(next:number){setPlaying(false);setStep(next);}
  function csv(){
    const heading='Kayıt;Yöntem;Dakika;Karşılanan müşteri talebi (L/s);Beklenen (L/s);Eksik (L/s);Ham SHA-256';
    const rows=plans.flatMap(plan=>{
      const values=net.traces[plan];
      return timeline.map((time,i)=>[net.run,plan,time,values.delivered_lps[i],values.expected_lps[i],
        values.deficit_lps[i],values.raw_sha256].join(';'));
    });
    download('SebekeKalkan-Net2-G4-C1-zaman-serisi.csv','\ufeff'+[heading,...rows].join('\r\n'),'text/csv;charset=utf-8');
  }
  return <>
    <a className="skip" href="#icerik">İçeriğe geç</a>
    <header className="top"><div className="shell nav">
      <a className="brand" href="#icerik"><Logo/>ŞebekeKalkan</a>
      <nav aria-label="Gezinme"><a href="#gosterim">Gösterim</a><a href="#arastirma">Bilimsel kanıt</a><a href="#senaryo">Kendi senaryon</a></nav>
    </div></header>
    <main className="shell" id="icerik">
      <section className="intro" aria-labelledby="title">
        <p className="kicker">BAÜN PROJE PAZARI <span>26 KASIM 2026</span></p>
        <h1 id="title">Su şebekesinde önce hangi arızaya müdahale edilmeli?</h1>
        <p>ŞebekeKalkan onarım seçeneklerinin su hizmetine etkisini hesaplar.</p>
      </section>
      <section className="dashboard" id="gosterim" aria-label="Net2 kayıtlı simülasyon karşılaştırması" data-mode={proof.mode}>
        <div className="map-card">
          <div className="map-heading"><div><h2>Onarım anında şebeke</h2><span>Net2 · Dört izolasyon · Bir ekip</span></div>
            <output htmlFor="time" aria-live="off" data-testid="time-label">{clock(minute)}</output>
          </div>
          <div className="mode-switch" role="group" aria-label="Gösterilen onarım sırası">
            {plans.map(plan=><button key={plan} type="button" aria-pressed={mode===plan} onClick={()=>setMode(plan)}>{names[plan]}</button>)}
          </div>
          <NetworkStage diagram={diagram} name="Net2" pressures={pressures} marks={marks}/>
          <div className="legend" aria-label="Düğüm basıncı">
            {BANDS.map(([key,label])=><span className={key} key={key}><i/>{label}</span>)}
            <span className="pipe-key"><i/>İzole boru</span>
          </div>
          <div className="timebar">
            <button type="button" aria-label={playing?'Zamanı duraklat':'Zamanı oynat'} onClick={()=>{
              if(step===timeline.length-1)setStep(0);
              setPlaying(!playing);
            }}>{playing?'Duraklat':'Oynat'}</button>
            <label className="visually-hidden" htmlFor="time">Simülasyon zamanı</label>
            <input type="range" id="time" min="0" max={timeline.length-1} value={step}
              aria-valuetext={clock(minute)} onChange={e=>move(Number(e.target.value))}/>
            {[120,480].map(t=><button type="button" key={t} className="tick" aria-pressed={minute===t}
              onClick={()=>move(timeline.indexOf(t))}>{clock(t)}</button>)}
          </div>
        </div>
        <div className="evidence-card">
          <p className="state"><span/> Doğrulanmış simülasyon kaydı</p>
          <p className="impact" data-testid="main-gain">%{num(net.percent)}</p>
          <h2>Daha düşük ağırlıklı hizmet açığı</h2>
          <p className="context">{net.id} · Güçlü tekli etki/süre yöntemine göre</p>
          <div className="pair instant" aria-label="Seçili saatte karşılanan talep">
            <p className="pair-label">{clock(minute)} · Karşılanan müşteri talebi</p>
            {plans.map(plan=><div key={plan} className={mode===plan?'focus':''}>
              <span className="plan-cell">{names[plan]}<small aria-label="Boru önceliği">{net.methods[plan].order.join(' → ')}</small></span>
              <strong>{num(net.traces[plan].delivered_lps[step])} <small>L/s</small></strong>
            </div>)}
          </div>
          <div className="small-metrics">
            <p><strong>34,5 → 31,5</strong><span>Kritik düşük basınç · düğüm-saat</span></p>
            <p><strong>16. saat</strong><span>İki planın son onarımı</span></p>
          </div>
        </div>
      </section>
      <p className="map-note">Düğüm renkleri ölçülen simülasyon basıncını gösterir. Boru geometrisi şematiktir.</p>
      <section className="below" aria-labelledby="schedule">
        <div className="section-title"><h2 id="schedule">İki onarım sırası</h2><p>İzolasyon 02.00’de başlar. Çizelge, simülasyon saatini kullanır.</p></div>
        <div className="schedules">{plans.map(plan=><article key={plan}><h3>{names[plan]}</h3><ol>
          {net.methods[plan].assignments.map(item=><li key={item.pipe_id}><b>{item.pipe_id}</b>
            <span>{clock(item.starts_at_h*60)}–{clock(item.ends_at_h*60)}</span></li>)}
        </ol><strong>{num(net.methods[plan].metrics.weighted_unmet_volume_m3,3)} ağırlıklı m³ hizmet açığı</strong></article>)}</div>
        <details><summary>Vaka kaynağı ve indirmeler</summary>
          <dl><dt>Kayıt kimliği</dt><dd><code>{net.run}</code></dd><dt>Sonuç SHA-256</dt><dd><code>{net.sha256}</code></dd>
            {plans.map(plan=><div key={plan}><dt>{names[plan]} ham SHA-256</dt><dd><code>{net.traces[plan].raw_sha256}</code></dd></div>)}
          </dl>
          <div className="actions"><button type="button" onClick={csv}>Zaman serisi CSV</button>
            <button type="button" onClick={()=>download('SebekeKalkan-dogrulanmis-kayit.json',JSON.stringify(proof,null,2),'application/json')}>Kanıt JSON</button></div>
        </details>
      </section>
      <section className="research below" id="arastirma" aria-labelledby="new-proof">
        <article className="research-score">
          <p className="state"><span/> Yeni doğrulanmış araştırma örneği</p>
          <h2 id="new-proof">%{num(mu.percent)}</h2>
          <p>{mu.id} · Sentetik ağ, seçilmiş doğrulanmış vaka</p>
        </article>
        <div>
          <h3>Aynı bitiş, daha düşük hizmet açığı</h3>
          <p><strong>{num(mu.reference,3)} → {num(mu.candidate,3)} ağırlıklı m³.</strong> Son onarım iki planda 16. saatte. Güçlü tekli etki/süre yöntemi {mu.calls.greedy}, B6 {mu.calls.s02_b6} WNTR çağrısı yaptı.</p>
          <details><summary>Araştırmanın kapsamı ve tüm sonuçlar</summary>
            <p>{study.clusters} arıza kümesi, {study.main} bağlı ana koşul. {study.primary} birincil kıyasta {study.WIN} kazanım, {study.TIE} eşitlik, {study.LOSS} kayıp. Eksik {study.main-study.primary} koşulun {study.SOLVER_ERROR}’ü çözücü hatası, {study.PHYSICAL_INVALID}’si fizik reddi, {study.TIMEOUT}’i zaman aşımı. Tüm yöntemleri {study.all_methods} iş tamamladı. Duyarlılıkta {study.sensitivity}/{study.sensitivity_total} kıyas yapılabildi.</p>
            <p>Üç MuR topolojisi aynı sentetik üretici ailesinden. MuR0006’da on kıyasta referansın birincil açığı sıfır. Skeletonize’ın önceki dış değerlendirmesinde altı koşulda kazanım bulunmadı. Kanıt, belirli simülasyon koşullarında ek kazanımı destekliyor. Saha tasarrufu ve genel üstünlük için kanıt yetersiz.</p>
            <p>Kayıt <code>{mu.run}</code><br/>Sonuç SHA-256 <code>{mu.sha256}</code></p>
            {!offline&&<p><a href={researchPage}>Kaynaklı araştırma eki</a></p>}
          </details>
        </div>
      </section>
      <section className="below live" id="senaryo" aria-labelledby="live-title">
        <h2 id="live-title">Kendi senaryon</h2>
        <p>Net2 veya Skeletonize’da üç ya da dört boru, bir ya da iki ekip seçin. Her yeni iş WNTR ile çözülür ve indirmeler fizik kabulünden sonra açılır.</p>
        {live==='local'?<a className="primary" href="/final-v4/senaryo">Yerel WNTR moduna geç</a>:
          live==='remote'?<a className="primary" href={apiBase+'/final-v4/senaryo'}>Canlı WNTR moduna geç</a>:
          <p role="status" className="live-state">{live==='checking'?'WNTR bağlantısı kontrol ediliyor.':'Bu gösterimde canlı WNTR sunucusu bağlı değil. Kayıtlı karşılaştırma kullanılabilir.'}</p>}
      </section>
      <footer>ŞebekeKalkan · Öğr. Gör. Enise Odabaş ve Öğr. Gör. Mert Hızmalı</footer>
    </main>
  </>;
}

createRoot(document.getElementById('root')!).render(<Service/>);
