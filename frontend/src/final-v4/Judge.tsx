import {useEffect, useState} from 'react';
import {API, fetchJson, format, METRICS, NAMES} from './domain';
import type {Counts, Research, RunView} from './domain';
import {Alternatives, Decision, ServiceChart, TraceWorkbench} from './Results';
import './v4.css';

const CASES = [['Net2_G4_C1','Ana vaka · Net2'],['Skeletonize_G1_C1','Dış ağ · Skeletonize']] as const;
const GROUPS: Record<string,string> = {dev:'Net2 geliştirme',internal_holdout:'Net2 iç değerlendirme',
  external_holdout:'Skeletonize dış değerlendirme',sprint01:'Sprint 01 ana deney',historical:'Tarihsel deney'};
type Card = {case_id:string;group:string;status:string};

export function Header({custom=false}:{custom?:boolean}) {
  const [full,setFull]=useState(false);
  const [unavailable,setUnavailable]=useState(false);
  useEffect(()=>{
    const change=()=>setFull(Boolean(document.fullscreenElement));
    const escape=(event:KeyboardEvent)=>{
      if(event.key==='Escape'&&document.fullscreenElement)void document.exitFullscreen().catch(()=>{});
    };
    document.addEventListener('fullscreenchange',change);
    document.addEventListener('keydown',escape);
    return ()=>{
      document.removeEventListener('fullscreenchange',change);
      document.removeEventListener('keydown',escape);
    };
  },[]);
  async function toggle() {
    try{
      if(document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {setUnavailable(true);}
  }
  return <header className="v4-header">
    <a href="#v4-main" className="v4-skip">İçeriğe geç</a>
    <div><a className="v4-brand" href="/final-v4">
      <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 2 29 8v9c0 7-8 11-13 14C11 28 3 24 3 17V8Z M8 17h7l4-7 5 10"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/></svg><strong>ŞebekeKalkan</strong></a>
      <nav aria-label="Uygulama bölümleri"><a href="/final-v4">Jüri gösterimi</a>
        {custom&&<a href="/final-v4/senaryo">Kendi senaryon</a>}<a href="/final-v4#v4-science">Bilimsel kanıt</a></nav>
      <button type="button" className="v4-full" onClick={()=>void toggle()}>{full?'Tam ekrandan çık':'Tam ekran'}</button>
    </div>
    {unavailable&&<p role="status">Bu tarayıcıda tam ekran açılamadı.</p>}
  </header>;
}

function Science({research,cards}:{research:Research|null;cards:Card[]|null}) {
  const summary=(c:Counts)=>[c.WIN||0,c.TIE||0,c.LOSS||0];
  const gap=research?.gap.find(x=>x.method==='s02_b6');
  const best=research?.gap.find(x=>x.method==='oracle');
  const groups=research?Object.entries(research.groups):[];
  const external=research?.groups.external_holdout;
  return <section id="v4-science" className="v4-panel v4-science">
    <div className="v4-panel-head"><div><h2>Bilimsel kanıt</h2>
      <p>S02-B6 ve güçlü tekli etki/süre referansı · Birincil ölçüt ağırlıklı hizmet açığı</p></div>
      <a href="/final" className="v4-link-button">Sprint 03 arşivini aç</a></div>
    {research&&<>
      <div className="v4-census">
        {[...groups,['Tümü',research.total] as const].map(([key,c])=>{
          const [win,tie,loss]=summary(c);
          return <article key={key}><h3>{GROUPS[key]||key} · {win+tie+loss} koşul</h3>
            <p>{win} kazanım / {tie} eşitlik / {loss} kayıp</p>
            <div aria-hidden="true">{[win,tie,loss].map((n,i)=><i key={i} style={{flexGrow:n}}/>)}</div></article>;
        })}
      </div>
      <div className="v4-science-scope">
        <h3>Sınırlamalar ve sonraki doğrulama</h3>
        {external&&<p><strong>Skeletonize dış ağında {summary(external)[0]}/{summary(external).reduce((a,b)=>a+b,0)} kazanım.</strong> Genel yöntem üstünlüğü doğrulanmadı. Ekip varyantları aynı arıza kümelerini paylaşır.</p>}
        <p>B6 aday havuzunda FIFO ve güçlü referans bulunur. 24 tam sayım yalnız beklemesiz onarım önceliklerini kapsar.</p>
        <p>Bu sürüm WNTR fiziği ve aday araması kullanır. Makine öğrenmesi ve üretken yapay zekâ kullanılmadı. Ağırlıklı m³, modeldeki hizmet açığıdır. Saha su tasarrufu ölçülmedi.</p>
        <p>Sıradaki doğrulama alanları saha kalibrasyonu, vana izolasyonu, ekip ulaşımı, belirsiz onarım süreleri, operatör değerlendirmesi ve daha çok dış ağdır.</p>
      </div>
      <details className="v4-details"><summary>Araştırma kapsamı ve sınırlamalar</summary>
        {gap&&best&&<p>Net2_G1_C1’de B6 {format(Number(gap.weighted_unmet_volume_m3),6)} ağırlıklı m³ buldu.
          Tam sayımın {format(Number(best.weighted_unmet_volume_m3),6)} ağırlıklı m³ sonucuna göre fark {format(Number(gap.weighted_unmet_volume_m3)-Number(best.weighted_unmet_volume_m3),6)} ağırlıklı m³.
          Tam sayım dört borunun 24 beklemesiz öncelik sırasını kapsar.</p>}
        <h3>Kötüleşen ölçütler</h3>
        <ul>{research.losses.map(row=>{
          const [,,unit]=METRICS.find(m=>m[0]===row.metric)!;
          return <li key={row.case+row.metric}>{row.case} · {NAMES[row.proposal]} ve {NAMES[row.baseline]} · {
            METRICS.find(m=>m[0]===row.metric)![1]} {format(row.baseline_value,6)} → {format(row.proposal_value,6)} {unit}</li>;
        })}</ul>
        <a href="/api/final/v1/research/chart.svg" download>Araştırma dağılımı SVG</a>
        <p className="v4-hash">{research.source} · {research.source_sha256}</p>
      </details></>}
    <details className="v4-details"><summary>Yedi kayıt ve tam kaynakları</summary>
      <p>Sprint 01, Sprint 02 ve tarihsel sonuçlar kendi kapsamlarıyla açılır.</p>
      {cards&&<ul className="v4-catalog">
        {cards.map(c=><li key={c.case_id}><strong>{c.case_id}</strong><span>{GROUPS[c.group]}</span>
          {c.status==='verified'?<a href={`/api/final/v1/cases/${c.case_id}/evidence`} target="_blank" rel="noreferrer">Kanıt JSON</a>:<span>Kaynak doğrulanamadı</span>}</li>)}
      </ul>}
    </details>
  </section>;
}

export default function Judge() {
  const [selected,setSelected]=useState({id:CASES[0][0] as string, attempt:0});
  const [view,setView]=useState<RunView|null>(null);
  const [failure,setFailure]=useState('');
  const [research,setResearch]=useState<Research|null>(null);
  const [scienceError,setScienceError]=useState(false);
  const [cards,setCards]=useState<Card[]|null>(null);
  useEffect(()=>{
    document.title='ŞebekeKalkan | Jüri gösterimi';
    const c=new AbortController();
    fetchJson<Research>(API+'/research',{signal:c.signal}).then(setResearch).catch(()=>{if(!c.signal.aborted)setScienceError(true);});
    fetchJson<Card[]>('/api/final/v1/catalog',{signal:c.signal}).then(setCards).catch(()=>{});
    return ()=>c.abort();
  },[]);
  useEffect(()=>{
    const c=new AbortController();
    fetchJson<RunView>(API+'/recorded/'+selected.id,{signal:c.signal}).then(data=>{
      if(!c.signal.aborted)setView(data);
    }).catch(e=>{if(!c.signal.aborted)setFailure(e.message);});
    return ()=>c.abort();
  },[selected]);
  function choose(id:string) {
    setView(null);setFailure('');setSelected(old=>({id,attempt:old.attempt+1}));
  }
  async function save(path:string) {
    try {
      const r=await fetch(API+'/recorded/'+selected.id+path,{cache:'no-store'});
      if(!r.ok) throw new Error();
      const url=URL.createObjectURL(await r.blob());
      const link=document.createElement('a');
      link.href=url;link.download=selected.id+(path?'.svg':'.json');link.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch {setView(null);setFailure('Kayıt ve ham zaman serisi doğrulanamadı. Ölçüt ve animasyon kapalı.');}
  }
  return <div className="v4">
    <Header custom/>
    <main className="v4-main" id="v4-main">
      <section className="v4-intro v4-intro-judge">
        <div><p className="v4-tag">Kayıtlı ve doğrulanmış sonuç</p>
          <h1>Hangi arızaya önce müdahale edilmeli?</h1>
          <p>Dört eşzamanlı boru arızasında onarım sıralarının su hizmetine etkisini karşılaştırın.</p></div>
        <div className="v4-case-switch v4-switch" aria-label="Kayıtlı vakalar">
          {CASES.map(([id,label])=><button type="button" key={id} aria-pressed={selected.id===id} onClick={()=>choose(id)}>{label}</button>)}
        </div>
      </section>
      {failure?<div className="v4-panel v4-warn" role="alert"><strong>{failure}</strong>
        <button type="button" onClick={()=>choose(selected.id)}>Kaynağı yeniden denetle</button></div>:
        !view?<div className="v4-panel v4-loading" role="status">Kayıt ve ham zaman serisi doğrulanıyor.</div>:
        <>
          <div className="v4-work-grid" id="v4-proof-overview" key={view.case_id}>
            <TraceWorkbench data={view}/>
            <Decision data={view}/>
          </div>
          <Alternatives data={view}/><ServiceChart key={view.case_id} data={view}/>
          <section className="v4-panel v4-provenance"><h2>Bu vakanın kaynağı</h2>
            <p>{view.case_id} · {GROUPS[view.group]} · {String(view.evidence.solver)}</p>
            <div className="v4-actions"><button type="button" onClick={()=>void save('/chart.svg')}>Karşılaştırma SVG</button>
              <button type="button" onClick={()=>void save('')}>Ham zaman verisi JSON</button></div>
            <details className="v4-details"><summary>Kayıt kimliği ve fizik kapıları</summary>
              <dl>{Object.entries(view.evidence).filter(([,v])=>v!==null).map(([key,value])=><div key={key}>
                <dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
              {Object.entries(view.methods).map(([key,method])=><details key={key}><summary>{NAMES[key]} fizik kanıtı</summary><pre>{JSON.stringify(method.physics,null,2)}</pre></details>)}
            </details>
          </section>
        </>}
      {scienceError&&<p role="alert">Araştırma karşılaştırması doğrulanamadı.</p>}
      <Science research={research} cards={cards}/>
    </main>
  </div>;
}
