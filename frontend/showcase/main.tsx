import {useCallback, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Dashboard, Schedule} from './Dashboard';
import Research from './Research';
import {isolationMinute, lastRepairMinute, timeline} from './record';
import type {Plan} from './record';
import './showcase.css';

const github = 'https://github.com/HIZMALI/SebekeKalkan';
const offline = window.location.protocol === 'file:';
const apiBase = offline ? '' : import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? '';
const local = /^(127\.0\.0\.1|localhost|\[::1\])$/.test(window.location.hostname);
const route = window.location.pathname.replace(/index\.html$/, '');
const researchPage = offline ? 'https://hizmali.github.io/SebekeKalkan/research/arastirma.html' :
  route !== '/demo/' && route.endsWith('/demo/') ? '../research/arastirma.html' : './research/arastirma.html';
const navLinks = [
  {href:'#gosterim', label:'Etkileşimli gösterim'}, {href:'#nasil-calisir', label:'Nasıl çalışır?'},
  {href:'#arastirma', label:'Araştırma sonuçları'}, {href:github, label:'GitHub'},
];
const lastStep = timeline.length - 1;

function Logo() {
  return <svg viewBox="0 0 36 36" aria-hidden="true">
    <path d="M18 2.5 32 8v10c0 7-6 12-14 15.5C10 30 4 25 4 18V8Z"/>
    <path d="m9 19 6-5 6 6 6-7"/><circle cx="9" cy="19" r="1.5"/><circle cx="27" cy="13" r="1.5"/>
  </svg>;
}

function Header() {
  return <header className="top">
    <div className="shell top-inner">
      <a className="brand" href="#icerik"><Logo/>ŞebekeKalkan</a>
      <nav className="desktop-nav" aria-label="Ana gezinme">
        {navLinks.map(link=><a key={link.href} href={link.href}>{link.label}</a>)}
      </nav>
      <details className="mobile-nav">
        <summary>Menü</summary>
        <nav aria-label="Ana gezinme">
          {navLinks.map(link=><a key={link.href} href={link.href}
            onClick={event=>event.currentTarget.closest('details')?.removeAttribute('open')}>{link.label}</a>)}
        </nav>
      </details>
    </div>
  </header>;
}

function LiveLink() {
  const [live,setLive] = useState<'checking' | 'local' | 'remote' | 'unavailable'>(local || apiBase ? 'checking' : 'unavailable');
  useEffect(()=>{
    if(!local && !apiBase) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(()=>controller.abort(), 3500);
    fetch(apiBase + '/healthz', {signal:controller.signal, cache:'no-store'})
      .then(response=>response.ok ? response.json() : Promise.reject())
      .then(data=>setLive(data.solver === 'WNTR' && data.live === 'local' && local ? 'local' :
        data.solver === 'WNTR' && data.live === 'isolated' && apiBase ? 'remote' : 'unavailable'))
      .catch(()=>setLive('unavailable')).finally(()=>clearTimeout(timeout));
    return ()=>{controller.abort(); clearTimeout(timeout);};
  }, []);

  return <section className="section scenario-link" id="senaryo" aria-labelledby="live-title">
    <div><h2 id="live-title">Kendi senaryon</h2><p>Yeni arıza, ekip ve süre girdileri gerçek WNTR oturumunda hesaplanır.</p></div>
    {live === 'local' ? <a className="button primary" href="/final-v4/senaryo">Yerel WNTR moduna geç</a> :
      live === 'remote' ? <a className="button primary" href={apiBase + '/final-v4/senaryo'}>Canlı WNTR moduna geç</a> :
      <p role="status">{live === 'checking' ? 'WNTR bağlantısı kontrol ediliyor.' : 'Bu sayfa doğrulanmış bir simülasyon kaydını gösterir. Canlı WNTR bağlantısı yok.'}</p>}
  </section>;
}

function Service() {
  const [plan, setPlan] = useState<Plan>('s02_b6');
  const [step, setStep] = useState(timeline.indexOf(480));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [inspected, setInspected] = useState<string | null>(null);
  const [jury, setJury] = useState(false);
  const workspace = useRef<HTMLElement>(null);
  const enterButton = useRef<HTMLButtonElement>(null);
  const exitButton = useRef<HTMLButtonElement>(null);
  const nativeFullscreen = useRef(false);

  useEffect(()=>{
    if (!playing) return;
    const timer = window.setInterval(()=>setStep(index=>Math.min(index + 1, lastStep)), 420 / speed);
    return ()=>window.clearInterval(timer);
  }, [playing, speed]);
  useEffect(()=>{
    if (step === lastStep && playing) setPlaying(false);
  }, [step, playing]);

  const move = useCallback((minute: number)=>{
    setPlaying(false);
    setStep(timeline.indexOf(minute));
  }, []);
  const togglePlay = useCallback(()=>{
    if (step === lastStep) setStep(0);
    setPlaying(value=>!value);
  }, [step]);

  const leaveJury = useCallback(()=>{
    setJury(false);
    if (document.fullscreenElement === workspace.current) void document.exitFullscreen().catch(()=>{});
    window.requestAnimationFrame(()=>enterButton.current?.focus());
  }, []);
  useEffect(()=>{
    function changed() {
      if (document.fullscreenElement === workspace.current) nativeFullscreen.current = true;
      else if (nativeFullscreen.current) {
        nativeFullscreen.current = false;
        leaveJury();
      }
    }
    document.addEventListener('fullscreenchange', changed);
    return ()=>document.removeEventListener('fullscreenchange', changed);
  }, [leaveJury]);

  useEffect(()=>{
    if (!jury) return;
    exitButton.current?.focus();
  }, [jury]);
  useEffect(()=>{
    if (!jury) return;
    function onKeys(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        leaveJury();
        return;
      }
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.target instanceof HTMLElement && event.target.closest('input, select, textarea, [contenteditable]')) return;
      if (event.key === '2' || event.key === '8' || event.key === 'Home' || event.key === 'End') {
        const targets = {'2':isolationMinute, '8':480, Home:timeline[0], End:lastRepairMinute};
        move(targets[event.key]);
      } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        const direction = event.key === 'ArrowRight' ? 1 : -1;
        setPlaying(false);
        setStep(index=>Math.min(lastStep, Math.max(index + direction, 0)));
      } else if (event.code === 'Space' && !(event.target instanceof Element && event.target.closest('button, a, summary, [role="button"]'))) {
        togglePlay();
      } else return;
      event.preventDefault();
    }
    window.addEventListener('keydown', onKeys);
    return ()=>window.removeEventListener('keydown', onKeys);
  }, [jury, leaveJury, move, togglePlay]);

  function enterJury() {
    setJury(true);
    void workspace.current?.requestFullscreen?.().catch(()=>{});
  }

  return <>
    {!jury&&<><a className="skip" href="#icerik">İçeriğe geç</a><Header/></>}
    <main className="shell" id="icerik">
      {!jury&&<section className="intro" aria-labelledby="title">
        <div>
          <p className="eyebrow recorded"><span aria-hidden="true"/>Doğrulanmış simülasyon kaydı</p>
          <h1 id="title">Doğru müdahale, doğru sırayla başlar.</h1>
          <p>Aynı arızalar, aynı ekip ve aynı onarım süreleri altında farklı müdahale sıralarının su hizmetine etkisini keşfedin.</p>
        </div>
        <button className="jury-entry" type="button" ref={enterButton} onClick={enterJury}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4H4v5m11-5h5v5m0 6v5h-5M4 15v5h5"/></svg>Jüri modu
        </button>
      </section>}
      <section id="gosterim" className={jury?'workspace workspace--jury':'workspace'} ref={workspace}
        aria-label="Etkileşimli Net2 gösterimi" data-jury={jury}>
        <Dashboard plan={plan} step={step} playing={playing} speed={speed} inspected={inspected} jury={jury}
          onPlan={setPlan} onMove={move} onPlay={togglePlay} onSpeed={setSpeed} onInspect={setInspected}
          onExit={leaveJury} exitRef={exitButton}/>
        {!jury&&<Schedule plan={plan} step={step}/>}
      </section>
      {!jury&&<>
        <Research researchPage={researchPage}/>
        <LiveLink/>
        <footer><a className="brand" href="#icerik"><Logo/>ŞebekeKalkan</a><span>Öğr. Gör. Enise Odabaş ve Öğr. Gör. Mert Hızmalı</span></footer>
      </>}
    </main>
  </>;
}

createRoot(document.getElementById('root')!).render(<Service/>);
