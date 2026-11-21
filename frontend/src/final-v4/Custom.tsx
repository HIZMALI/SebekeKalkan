import {useEffect, useMemo, useRef, useState} from 'react';
import NetworkStage from './NetworkStage';
import type {PipeMark} from './NetworkStage';
import {Header} from './Judge';
import {Alternatives, Decision, ServiceChart, TraceWorkbench} from './Results';
import {API, difference, fetchJson, format} from './domain';
import type {Diagram, RunView} from './domain';
import presetData from './presets.json';

const URL=API+'/custom';
const LIVE=new Set(['queued','running']);
const STATE:Record<string,string>={queued:'Sıraya alındı',running:'Hesaplanıyor',completed:'Fizik kabulü tamamlandı',
  failed:'Hesap başarısız',timeout:'Zaman aşımı',cancelled:'İptal edildi',interrupted:'Yarım kaldı'};
const FAILURE:Record<string,string>={
  PHYSICAL_INVALID:'Denenen en az bir plan fiziksel kabulü geçmedi. Plan ve indirmeler kapalı.',
  SOLVER_ERROR:'WNTR, denenen en az bir planın hidrolik çözümünü tamamlayamadı.',
  ORACLE_MISMATCH:'Taze yeniden çözüm ile aday sonucu uyuşmadı. Plan ve indirmeler kapalı.',
  WORKER_ERROR:'Yerel hesap süreci sonuç üretemedi.',
};
type Fault={pipe_id:string;repair_hours:number};
type Input={network:string;faults:Fault[];crews:number;search:'fast'|'comprehensive'};
type Model={network:string;diagram:Diagram;eligible:string[];critical_weights:Record<string,number>;source_sha256:string;
  settings:{start_hour:number;horizon_hours:number;step_minutes:number;minimum_pressure_m:number;required_pressure_m:number;low_pressure_m:number}};
type Options={networks:string[];diagnostic:boolean;timeout_seconds:number;search:string[]};
type Job={
  job_id:string;status:string;message:string;mode:string;request:Input;elapsed_seconds?:number;worker_exit_code?:number;
  failure_code?:string;method_version:string;solver:string;input_sha256:string;scenario_sha256:string;source_sha256:string;
  network_sha256:string;code_sha256:string;protocol_sha256:string;timeout_seconds:number;
  result?:{trial_count:number;wntr_calls:number;coverage:{candidate_budget:number;evaluated_candidates:number;total_priorities:number;
    complete_orders?:number;unique_schedules?:number;minimum_weighted_m3?:number;extra_seconds?:number;improvement_vs_fast_m3?:number}};
};
const defaults:Input={network:'Net2',faults:[],crews:1,search:'fast'};
const presets=presetData as {caseId:string;title:string;request:Input}[];

function sameInput(a:Input,b:Input) {
  return a.network===b.network&&a.crews===b.crews&&a.search===b.search&&a.faults.length===b.faults.length&&
    a.faults.every((f,i)=>f.pipe_id===b.faults[i].pipe_id&&f.repair_hours===b.faults[i].repair_hours);
}

function updateAddress(job?:string) {
  const url=new window.URL(window.location.href);
  if(job)url.searchParams.set('is',job);
  else url.searchParams.delete('is');
  window.history.replaceState(null,'',url);
}

export default function Custom() {
  const [options,setOptions]=useState<Options|null>(null);
  const [input,setInput]=useState<Input>(defaults);
  const [model,setModel]=useState<Model|null>(null);
  const [pipe,setPipe]=useState('');
  const [job,setJob]=useState<Job|null>(null);
  const [lookup,setLookup]=useState(()=>{
    const id=new URLSearchParams(window.location.search).get('is');
    return id&&/^[a-f0-9]{32}$/.test(id)?{id,revision:0}:null;
  });
  const restore=useRef(Boolean(lookup));
  const [view,setView]=useState<RunView|null>(null);
  const [notice,setNotice]=useState('');
  const [modelIssue,setModelIssue]=useState('');
  const [problem,setProblem]=useState('');
  const [submitting,setSubmitting]=useState(false);
  const [cancelling,setCancelling]=useState(false);
  const warnings=useRef<HTMLElement>(null);
  const selectedCount=input.faults.length;
  const busy=submitting||Boolean(job&&LIVE.has(job.status))||Boolean(lookup&&!job&&!problem);
  const verified=model?.network===input.network?model:null;
  const eligible=useMemo(()=>new Set(verified?.eligible||[]),[verified]);
  const marks=Object.fromEntries(input.faults.map((f,i)=>[f.pipe_id,{kind:'selected',label:String(i+1)}])) as Record<string,PipeMark>;
  const current=job?.result?.coverage;
  const fastGap=current?.minimum_weighted_m3===undefined||!view?null:
    difference(view.methods.s02_b6.metrics.weighted_unmet_volume_m3,current.minimum_weighted_m3,'weighted_unmet_volume_m3');

  useEffect(()=>{
    document.title='ŞebekeKalkan | Kendi senaryon';
    const c=new AbortController();
    fetchJson<Options>(URL+'/models',{signal:c.signal}).then(setOptions).catch(e=>{if(!c.signal.aborted)setProblem(e.message);});
    return ()=>c.abort();
  },[]);
  useEffect(()=>{
    const c=new AbortController();
    fetchJson<Model>(URL+'/models/'+encodeURIComponent(input.network),{signal:c.signal}).then(value=>{
      if(!c.signal.aborted){setModel(value);setModelIssue('');}
    }).catch(e=>{if(!c.signal.aborted)setModelIssue(e.message);});
    return ()=>c.abort();
  },[input.network]);
  useEffect(()=>{
    if(!lookup)return;
    const {id}=lookup;
    const c=new AbortController();
    let timer:number;
    async function poll(){
      try{
        const state=await fetchJson<Job>(URL+'/jobs/'+id,{signal:c.signal});
        if(c.signal.aborted)return;
        if(restore.current){
          setInput(state.request);
          restore.current=false;
        }
        setJob(state);setProblem('');
        if(LIVE.has(state.status)){timer=window.setTimeout(poll,750);return;}
        setCancelling(false);
        if(state.status==='completed'){
          const completed=await fetchJson<RunView>(URL+'/jobs/'+id+'/view',{signal:c.signal});
          if(c.signal.aborted)return;
          setView(completed);
        }
      }catch(e){
        if(c.signal.aborted)return;
        setView(null);setJob(null);setProblem(e instanceof Error?e.message:'Canlı iş kaydı okunamadı.');
      }
    }
    void poll();
    return ()=>{c.abort();window.clearTimeout(timer);};
  },[lookup]);

  function change(next:Input){
    setInput(next);setJob(null);setView(null);setLookup(null);setProblem('');setNotice('');
    updateAddress();
  }
  function toggle(id:string){
    if(busy||!eligible.has(id))return;
    const found=input.faults.some(f=>f.pipe_id===id);
    if(!found&&selectedCount===4){setNotice('En çok dört arıza seçilebilir. Önce bir boruyu kaldırın.');return;}
    const faults=found?input.faults.filter(f=>f.pipe_id!==id):[...input.faults,{pipe_id:id,repair_hours:3}];
    change({...input,faults,search:faults.length<4?'fast':input.search});
  }
  async function start(){
    setSubmitting(true);setJob(null);setView(null);setLookup(null);setProblem('');setNotice('');
    updateAddress();
    try {
      const state=await fetchJson<Job>(URL+'/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(input)});
      setJob(state);setLookup({id:state.job_id,revision:0});updateAddress(state.job_id);
      requestAnimationFrame(()=>warnings.current?.focus());
    }catch(e){setProblem(e instanceof Error?e.message:'Yerel iş başlatılamadı.');}
    finally{setSubmitting(false);}
  }
  async function cancel(){
    if(!job)return;
    setCancelling(true);
    try{await fetchJson(URL+'/jobs/'+job.job_id+'/cancel',{method:'POST'});}
    catch(e){setCancelling(false);setProblem(e instanceof Error?e.message:'İptal doğrulanamadı.');}
  }
  async function download(ext:string){
    if(!job||!view)return;
    try{
      const r=await fetch(URL+'/jobs/'+job.job_id+'/export/'+ext,{cache:'no-store'});
      if(!r.ok)throw new Error();
      const href=window.URL.createObjectURL(await r.blob());
      const link=document.createElement('a');
      link.href=href;link.download=`SebekeKalkan-V4-${job.job_id}.${ext}`;link.click();
      window.setTimeout(()=>window.URL.revokeObjectURL(href),1000);
    }catch{setView(null);setJob(null);setProblem('Kanıt yeniden doğrulanamadı. Sonuç ve indirmeler kapalı.');}
  }

  return <div className="v4">
    <Header custom/>
    <main className="v4-main" id="v4-main">
      <section className="v4-intro"><div><p className="v4-tag">Canlı WNTR simülasyonu</p>
        <h1>Onarım senaryonu kur</h1>
        <p>Kullanıcı tarafından oluşturulan, araştırma örnek şebekesinde canlı simülasyon. Bu sonuçlar 14 koşulluk araştırma serisine katılmaz.</p></div>
        <a className="v4-link-button" href="/final-v4">Kayıtlı jüri vakasına dön</a></section>
      {options?.diagnostic&&<p className="v4-warn">Bu oturum gerçek WNTR yakınsama hatası denetiminde çalışıyor. Sonuç yayımlanmaz.</p>}
      <section className="v4-panel" aria-labelledby="v41-presets">
        <h2 id="v41-presets">Hazır senaryolar</h2>
        <p>Önceden fizik kabulü geçen girdileri yükler. Dilediğiniz alanı değiştirin, ardından yeni WNTR hesabı başlatın.</p>
        <div className="v4-switch v4-preset-options">{presets.map(preset=>
          <button type="button" key={preset.caseId} disabled={busy||!options} aria-pressed={sameInput(input,preset.request)}
            onClick={()=>{setPipe('');setModelIssue('');change(preset.request);}}>{preset.title}</button>)}</div>
      </section>
      <div className="v4-custom-grid">
        <section className="v4-panel v4-builder">
          <div className="v4-panel-head"><div><h2>Şebekede boru seç</h2><p>Şema veya listedeki üç ya da dört uygun boruyu seçin.</p></div>
            <label>Örnek şebeke <select value={input.network} disabled={busy||!options} onChange={e=>{
              setPipe('');setModelIssue('');change({...defaults,network:e.target.value});
            }}>{(options?.networks||[input.network]).map(item=><option key={item}>{item}</option>)}</select></label></div>
          {modelIssue?<p role="alert" className="v4-warn">{modelIssue}</p>:verified?
            <NetworkStage key={verified.network} diagram={verified.diagram} name={verified.network} eligible={eligible}
              marks={marks} onSelect={busy?undefined:toggle}/>:<p role="status">Model ve boru izinleri denetleniyor.</p>}
          <div className="v4-actions v4-pipe-picker">
            <label>Boru listesi <select value={pipe} disabled={busy||!verified} onChange={e=>setPipe(e.target.value)}>
              <option value="">Boru seçin</option>{verified?.eligible.filter(id=>!marks[id]).map(id=><option key={id} value={id}>Boru {id}</option>)}</select></label>
            <button type="button" disabled={busy||!pipe||!eligible.has(pipe)} onClick={()=>{toggle(pipe);setPipe('');}}>Arıza ekle</button>
          </div>
          {notice&&<p role="status" className="v4-note">{notice}</p>}
          <p className="v4-muted">INP çizim koordinatları. Şema coğrafi harita veya ekip ulaşım rotası değildir.</p>
        </section>
        <section className="v4-panel v4-setup">
          <h2>Onarım girdileri</h2>
          <fieldset disabled={busy} className="v4-fields">
            <legend className="v4-sr">Ekipler, onarım süreleri ve arama bütçesi</legend>
            <label className="v4-inline">Ekip sayısı <select value={input.crews} onChange={e=>change({...input,crews:Number(e.target.value)})}>
              <option value={1}>1 ekip</option><option value={2}>2 ekip</option></select></label>
            <h3>Bildirim sırası · {selectedCount}/4 arıza</h3>
            {selectedCount?<ol className="v4-faults">{input.faults.map(f=><li key={f.pipe_id}>
              <strong>Boru {f.pipe_id}</strong>
              <label><span className="v4-sr">Boru {f.pipe_id} onarım süresi</span>
                <select value={f.repair_hours} onChange={e=>change({...input,faults:input.faults.map(o=>
                  o.pipe_id===f.pipe_id?{...o,repair_hours:Number(e.target.value)}:o)})}>
                  {[2,3,4,5].map(h=><option key={h} value={h}>{h} saat</option>)}</select>
              </label>
              <button type="button" onClick={()=>toggle(f.pipe_id)} aria-label={`Boru ${f.pipe_id} seçimini kaldır`}>Kaldır</button>
            </li>)}</ol>:<p>İlk boruyu şemadan veya listeden ekleyin.</p>}
            {selectedCount===4&&options?.search.includes('comprehensive')?<fieldset className="v4-search-mode">
              <legend>Arama kapsamı</legend>
              <label><input type="radio" name="search" checked={input.search==='fast'} onChange={()=>change({...input,search:'fast'})}/> Hızlı · B6 / 6 aday</label>
              <label><input type="radio" name="search" checked={input.search==='comprehensive'} onChange={()=>change({...input,search:'comprehensive'})}/> Kapsamlı · 24 sıra</label>
              <p>Tam tarama, ekiplerin beklemeden başladığı 24 onarım önceliğini inceler.</p>
            </fieldset>:selectedCount===3&&<p className="v4-note">Üç arıza için mevcut v2 karar kuralı. Altı öncelik sırası fiziksel olarak sınanır.</p>}
          </fieldset>
          {verified&&<details className="v4-details"><summary>Sabit fizik varsayımları</summary>
            <p>Arıza {verified.settings.start_hour}. saatte, ufuk {verified.settings.horizon_hours} saat, adım {verified.settings.step_minutes} dakika.
              Basınca bağlı talep {verified.settings.minimum_pressure_m} / {verified.settings.required_pressure_m} m eşikleri, kritik eşik {verified.settings.low_pressure_m} m.</p>
            <p>Ön kayıtlı düğüm ağırlıkları {Object.entries(verified.critical_weights).map(([id,w])=>`${id} × ${w}`).join(', ')}.</p>
          </details>}
          <button type="button" className="v4-primary" disabled={busy||selectedCount<3||!verified||!options} onClick={()=>void start()}>
            Canlı hesapla</button>
        </section>
      </div>
      <section className="v4-panel v4-live-status" tabIndex={-1} ref={warnings} aria-label="Canlı iş durumu" id="v4-live-status">
        <h2>Canlı iş</h2>
        {problem&&<p role="alert" className="v4-warn">{problem}</p>}
        {!job&&!problem&&<p>{submitting||lookup?'Yerel iş durumu okunuyor.':'Yeni canlı hesap başlatıldığında gerçek iş kimliği burada görünür.'}</p>}
        {problem&&lookup&&<button type="button" onClick={()=>setLookup(old=>old?{...old,revision:old.revision+1}:null)}>İşi yeniden denetle</button>}
        {job&&<>
          <p role="status"><strong>{STATE[job.status]}</strong> · {job.message}</p>
          <p className="v4-hash">İş {job.job_id} · {job.timeout_seconds} saniye sınırı</p>
          {job.failure_code&&<p className="v4-warn">{FAILURE[job.failure_code]||'Motor doğrulama hatası.'} <strong>{job.failure_code}</strong></p>}
          {LIVE.has(job.status)&&<button type="button" disabled={cancelling} onClick={()=>void cancel()}>{cancelling?'İptal bekleniyor':'İşi iptal et'}</button>}
          {view&&<>
            <p>{job.result?.trial_count} fizik denemesi · {job.result?.wntr_calls} gerçek WNTR çağrısı · {format(job.elapsed_seconds||0)} saniye</p>
            <div className="v4-actions">{['csv','json','pdf'].map(ext=><button type="button" key={ext} onClick={()=>void download(ext)}>{ext.toUpperCase()} indir</button>)}</div>
          </>}
          <details className="v4-details"><summary>İşin kaynağı ve çözücü</summary>
            <dl>{Object.entries({'Çözücü':job.solver,'Yöntem':job.method_version,'Ağ SHA-256':job.network_sha256,
              'Senaryo SHA-256':job.scenario_sha256,'Girdi SHA-256':job.input_sha256,'Motor SHA-256':job.source_sha256,
              'Kod SHA-256':job.code_sha256,'Protokol SHA-256':job.protocol_sha256,'İşçi çıkış kodu':job.worker_exit_code})
              .filter(([,v])=>v!=null).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          </details>
        </>}
        {(problem||Boolean(job&&['failed','timeout','interrupted','cancelled'].includes(job.status)))&&
          <a className="v4-link-button v4-return" href="/final-v4">Kayıtlı jüri gösterimini aç</a>}
      </section>
      {view&&current&&<>
        <section className="v4-panel" aria-label="Arama kapsamı ve maliyet">
          <h2>Arama kapsamı ve maliyet</h2>
          {job?.request.faults.length===3?
            <p>V2 karar kuralı · {current.evaluated_candidates} fiziksel aday · {current.total_priorities} olası öncelik</p>:
            <p>{current.evaluated_candidates} fiziksel aday · hızlı bütçe {current.candidate_budget} · {current.total_priorities} olası öncelik</p>}
          {current.complete_orders&&<>
            <p>Kapsamlı tarama {current.complete_orders} önceliğin tamamını çözdü. {current.unique_schedules} farklı hidrolik çizelge.
              Ek süre {format(current.extra_seconds!)} saniye.</p>
            <p>24 sıra içinde en düşük ağırlıklı açık {format(current.minimum_weighted_m3!,6)} ağırlıklı m³. {
              fastGap===0?'B6 ile protokol toleransı içinde eşit.':`B6 ile fark ${format(current.improvement_vs_fast_m3!,6)} ağırlıklı m³.`}</p>
            <p>Bu kapsam sabit ekip ve sürelerle, beklemesiz arızalara atanmayı temsil eder. Ulaşım ve saha koşulları kapsam dışıdır.</p>
          </>}
        </section>
        <div className="v4-work-grid" key={view.case_id}><TraceWorkbench data={view}/><Decision data={view}/></div>
        <Alternatives data={view}/><ServiceChart key={view.case_id} data={view}/>
      </>}
    </main>
  </div>;
}
