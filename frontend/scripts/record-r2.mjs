import {chromium} from '../node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
const root=path.resolve('..'),S=process.env.R2_PROJECT==='SebekeKalkan',out=process.env.R2_CAPTURE_ROOT;
if(!out)throw new Error('R2_CAPTURE_ROOT gerekli');await fs.mkdir(path.join(out,'ham'),{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({baseURL:process.env.R2_BASE_URL,viewport:{width:1920,height:1080},recordVideo:{dir:path.join(out,'ham'),size:{width:1920,height:1080}},locale:'tr-TR',timezoneId:'Europe/Istanbul',acceptDownloads:true});
await context.tracing.start({screenshots:true,snapshots:true,sources:true});const page=await context.newPage(),events=[],errors=[];page.on('pageerror',e=>errors.push(e.message));const started=Date.now();let status='FAILED',computeStart=0,computeEnd=0;
async function caption(text,ms=2600){events.push({elapsed_ms:Date.now()-started,text});await page.evaluate(t=>{let el=document.getElementById('capture-caption');if(!el){el=document.createElement('div');el.id='capture-caption';el.style.cssText='position:fixed;left:28px;right:28px;bottom:16px;z-index:99999;padding:14px 22px;background:#fffef8f5;border-left:6px solid #087d87;font:600 25px Arial;color:#17374d;box-shadow:0 2px 10px #0002;pointer-events:none';document.body.appendChild(el);}el.textContent=t;},text);await page.waitForTimeout(ms);}
let result;
try{
 await page.goto('/');
 if(!S){
  await page.getByText('35.040',{exact:false}).first().waitFor();await caption('UCI: 35.040 gerçek tüketim kaydı. İş emirleri bu ölçümlerden türetilmez.',3500);
  await page.getByRole('button',{name:'Rehberli planlamayı başlat',exact:true}).click();await caption('Sekiz iş ve iki üretim hattı açıldı. Fiyat dosyası ayrıca seçiliyor.',2000);
  const upload=page.waitForResponse(r=>r.url().endsWith('/api/fiyat/yukle')&&r.request().method()==='POST');
  await page.getByLabel('Fiyat dosyası yükle',{exact:true}).setInputFiles(path.join(root,'data/raw/price_2026-10-27_28_secondary.csv'));
  const loaded=await(await upload).json();if(!loaded['menşei']?.dogrulama?.includes('ikincil'))throw new Error('Fiyat menşei doğru korunmadı');
  await caption('İkincil fiyat CSV dosyası yüklendi. Doğrudan EPİAŞ doğrulaması yoktur.',3000);
  await page.getByLabel('Toplam güç limiti',{exact:true}).fill('14');await page.locator('table').first().scrollIntoViewIfNeeded();await caption('Sekiz işin süreleri, güçleri, makine ve öncül kısıtları aynı tutulur.',3000);
  const posted=page.waitForResponse(r=>r.url().endsWith('/api/planla')&&r.request().method()==='POST');computeStart=Date.now()-started;
  await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();await caption('Üç plan gerçekten hesaplanıyor. Tamamlandığında sonuçlar açılır.',1800);result=await(await posted).json();
  await page.getByRole('heading',{name:'Aynı kısıtlar, üç farklı karar'}).waitFor();computeEnd=Date.now()-started;
  if(!result.planlar?.every(x=>['OPTIMAL','FEASIBLE_TIMEOUT'].includes(x.durum)))throw new Error('Uygun üç plan yok');
  await caption('Hesaplama tamamlandığında maliyet ve tepe güç birlikte karşılaştırılır.',4200);
  await page.locator('.comparison').screenshot({path:path.join(out,'gercek_karsilastirma.png')});
  for(const label of ['Erken uygulanabilir','Maliyet odaklı','Dengeli yük']){await page.getByRole('button',{name:new RegExp(label)}).first().click();await caption(label+': aynı iş yükü, farklı amaç. Enerji ve karbon tasarrufu iddiası yok.',2400);}
  await page.getByRole('heading',{name:/İş çizelgesi/}).scrollIntoViewIfNeeded();await caption('Başlangıç ve bitişler gerçek çözümden gelir. Uygunluk ayrıca denetlenir.',3000);
  await page.evaluate(()=>window.scrollTo({top:0}));
  for(const label of ['CSV indir','Deney JSON’u','PDF raporu']){const wait=page.waitForEvent('download');await page.getByRole('link',{name:label,exact:true}).click();const f=await wait;await f.saveAs(path.join(out,f.suggestedFilename()));}
  await caption('CSV, JSON ve PDF indirildi. Sonuç, seçilen fiyat ve üretim kısıtlarıyla geçerlidir.',4500);
 }else{
  await page.getByRole('button',{name:'Örnek senaryo yükle',exact:true}).waitFor();await caption('Net3 mühendislik test ağı. BASKİ saha şebekesi veya kaçak ölçümü değildir.',3000);
  await page.getByRole('button',{name:'Örnek senaryo yükle',exact:true}).click();await page.getByLabel('Ekip sayısı',{exact:true}).fill('1');await caption('Üç boru seçildi. Ekip ve onarım süreleri kullanıcı girdisidir.',2500);
  await page.getByLabel('Ekip sayısı',{exact:true}).fill('2');await page.getByLabel('Onarım süresi (saat)',{exact:true}).first().fill('2');await caption('İki ekip, üç arıza. Aynı süreler ve fiziksel koşullarda bütün sıralar karşılaştırılır.',2500);
  const post=page.waitForResponse(r=>r.url().endsWith('/api/v2/experiments')&&r.request().method()==='POST');computeStart=Date.now()-started;await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();await caption('Gerçek WNTR/v2 hesabı sürüyor. Tamamlandığında fiziksel kabul gösterilir.',1800);const id=(await(await post).json()).id;
  await page.getByRole('region',{name:'Plan sonuçları',exact:true}).waitFor({timeout:190000});computeEnd=Date.now()-started;const job=await(await page.request.get('/api/v2/experiments/'+id)).json();result=job.result;if(job.status!=='completed'||!result.physical_validation.pass)throw new Error('Fiziksel kabul yok');
  await page.getByRole('region',{name:'Karar özeti',exact:true}).scrollIntoViewIfNeeded();await caption('Hesaplama tamamlandığında eşit hacim ve son onarım süresi ayrı okunur.',4000);
  await page.getByRole('region',{name:'Karar özeti',exact:true}).screenshot({path:path.join(out,'gercek_karsilastirma.png')});
  await page.evaluate(()=>{const el=document.querySelector('#network-svg');if(el)window.scrollTo({top:scrollY+el.getBoundingClientRect().top-65});});await page.getByLabel('Zaman adımı',{exact:true}).fill('8');await caption('2. saatte üç hat kapalıdır. Kırmızı çizgiler gerçek bağlantı durumudur.',3000);
  await page.getByRole('button',{name:'Zamanı oynat',exact:true}).click();await caption('Zaman oynatılıyor. Onarım bittiğinde hat ve basınç görünümü değişir.',4600);if(await page.getByRole('button',{name:'Duraklat',exact:true}).count())await page.getByRole('button',{name:'Duraklat',exact:true}).click();await page.getByLabel('Zaman adımı',{exact:true}).fill('28');await caption('7. saatte onarımlar tamamlanır. Hizmet açığı, sızan su miktarı değildir.',3000);
  await page.getByRole('region',{name:'Karar özeti',exact:true}).scrollIntoViewIfNeeded();
  for(const label of ['Deney JSON','Sonuç CSV','PDF raporu']){const wait=page.waitForEvent('download');await page.getByRole('link',{name:label,exact:true}).click();const f=await wait;await f.saveAs(path.join(out,f.suggestedFilename()));}
  await caption('Karar, girdiler ve sonuçlar indirildi. Net3 dışındaki saha etkisi doğrulanmadı.',4200);
 }
 await fs.writeFile(path.join(out,'calculated_result.json'),JSON.stringify(result,null,2));await page.screenshot({path:path.join(out,'son_ekran.png')});
 const padding=58000-(Date.now()-started);if(padding>0)await page.waitForTimeout(padding);
 if(errors.length)throw new Error(errors.join(';'));status='COMPLETED';
}finally{
 await context.tracing.stop({path:path.join(out,'kaynak_iz.zip')});const video=page.video();await context.close();await fs.writeFile(path.join(out,'capture.json'),JSON.stringify({status,elapsed_ms:Date.now()-started,raw_video:await video.path(),viewport:{width:1920,height:1080},computeStart,computeEnd,events,page_errors:errors},null,2));await browser.close();
}
if(status!=='COMPLETED')process.exitCode=1;
