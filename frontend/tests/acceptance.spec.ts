import {test,expect,Page} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const root=path.resolve('..');
const imagePrefix=process.env.SE_IMAGE_PREFIX||'BUILD01_S';
const errors=new Map<Page,string[]>();
test.beforeEach(async({page})=>{
  errors.set(page,[]);
  page.on('pageerror',e=>errors.get(page)!.push(e.message));
  await page.goto('/?surum=v1');
  await expect(page.getByRole('button',{name:'Örnek senaryo yükle',exact:true})).toBeEnabled();
});
test.afterEach(async({page},info)=>{
  expect(errors.get(page)).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await info.attach('tarayıcı.json',{body:JSON.stringify({browser:page.context().browser()?.version(),project:info.project.name,pageerrors:errors.get(page),width:await page.evaluate(()=>innerWidth)},null,2),contentType:'application/json'});
});
async function example(page:Page){await page.getByRole('button',{name:'Örnek senaryo yükle',exact:true}).click();await expect(page.getByRole('button',{name:'Boru 137 arızasını kaldır',exact:true})).toBeVisible();}
async function calculate(page:Page){
  const response=page.waitForResponse(r=>r.url().endsWith('/api/experiments')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();
  const id=(await (await response).json()).id;
  await expect(page.getByRole('region',{name:'Plan sonuçları'})).toBeVisible({timeout:95000});
  const result=await (await page.request.get(`/api/experiments/${id}/export/json`)).json();
  return {id,result};
}
async function advanced(page:Page){await page.getByText('Yöntem ayarları ve elle sıra',{exact:true}).click();}

test('tam model yükleme, arıza ekleme ve silme',async({page})=>{
  await page.getByText('Ağ dosyasını doğrula',{exact:true}).click();
  const input=page.getByLabel('Tam ağ dosyası',{exact:true});
  await input.setInputFiles({name:'bos.inp',mimeType:'application/octet-stream',buffer:Buffer.alloc(0)});
  await expect(page.getByRole('alert')).toContainText('Ağ dosyası boş');
  await input.setInputFiles({name:'bozuk.inp',mimeType:'application/octet-stream',buffer:Buffer.from('broken')});
  await expect(page.getByRole('alert')).toContainText('eşleşmiyor');
  await input.setInputFiles(path.join(root,'data/networks/Net3.inp'));
  await expect(page.getByRole('status')).toContainText('özeti doğrulandı');
  await page.getByLabel('Boru seç',{exact:true}).selectOption('137');
  await page.getByRole('button',{name:'Ekle / kaldır',exact:true}).click();
  await expect(page.getByRole('button',{name:'Boru 137 arızasını kaldır',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Boru 137 arızasını kaldır',exact:true}).click();
  await expect(page.getByRole('button',{name:'Planları hesapla',exact:true})).toBeDisabled();
});

test('gerçek hesap, zaman çizelgesi, sayılar ve üç dışa aktarma',async({page},info)=>{
  await example(page);
  const {id,result}=await calculate(page);
  expect(result.search.oracle_verified).toBe(true);
  expect(result.search.candidate_count).toBe(6);
  await expect(page.getByRole('region',{name:'Plan sonuçları'})).toContainText('bağımsız referans doğrulandı');
  const m=result.methods.proposal;
  const slider=page.getByLabel('Zaman adımı',{exact:true});
  await slider.fill('8');
  await expect(page.locator('[data-pipe="137"]')).toHaveAttribute('stroke','#b42332');
  await page.getByRole('button',{name:'Zamanı oynat',exact:true}).click();
  await expect(page.getByRole('button',{name:'Duraklat',exact:true})).toBeVisible();
  await expect.poll(()=>slider.inputValue()).not.toBe('8');
  await page.getByRole('button',{name:'Duraklat',exact:true}).click();
  await slider.fill(String(m.times_seconds.length-1));
  await expect(page.locator('[data-pipe="137"]')).toHaveAttribute('stroke','#20805e');
  await expect(page.getByText('3 / 3 onarım tamamlandı',{exact:true})).toBeVisible();
  const p=m.pressure_m.at(-1)[m.node_ids.indexOf('203')];
  await expect(page.locator('.node-inspector').first()).toContainText(p.toLocaleString('tr-TR',{maximumFractionDigits:2}));
  await page.getByLabel('İncelenen bağlantı',{exact:true}).selectOption('137');
  await expect(page.locator('.node-inspector').last()).toContainText('m³/s');
  for(const [name,file] of [['Deney JSON','result.json'],['Sonuç CSV','summary.csv'],['Şemayı indir (SVG)','network.svg']]){
    const download=page.waitForEvent('download');
    await page.getByRole(name==='Şemayı indir (SVG)'?'button':'link',{name,exact:true}).click();
    const item=await download;
    await item.saveAs(info.outputPath(file));
    const content=await fs.readFile(info.outputPath(file),'utf8');
    if(file==='result.json')expect(JSON.parse(content).input_sha256).toBe(result.input_sha256);
    if(file==='summary.csv')expect(content).toContain(result.input_sha256);
    if(file==='network.svg')expect(content).toContain('ŞebekeKalkan');
  }
  await page.getByRole('button',{name:'Yakınlaştır',exact:true}).click();
  await expect(page.locator('.map-tools')).toContainText('150%');
  await page.getByRole('button',{name:'Sığdır',exact:true}).click();
  await page.getByRole('button',{name:'Bildirim sırası',exact:true}).click();
  await expect(page.getByRole('button',{name:'Bildirim sırası',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'ŞebekeKalkan önerisi',exact:true}).click();
  await slider.fill('8');
  await page.screenshot({path:info.outputPath(`${imagePrefix}_tam.png`),fullPage:true});
  await page.getByRole('region',{name:'Plan sonuçları'}).scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath(`${imagePrefix}_sonuc.png`)});
  await info.attach('deney.json',{body:JSON.stringify({id,input_sha256:result.input_sha256,metrics:result.methods.proposal.metrics,total_seconds:result.total_seconds}),contentType:'application/json'});
});

test('girdi değişince eski sonuç silinir, yeni ekip ve elle sıra gerçekten hesaplanır',async({page})=>{
  test.setTimeout(215000);
  await example(page);
  const before=await calculate(page);
  await page.getByLabel('Ekip sayısı',{exact:true}).fill('1');
  await expect(page.getByRole('region',{name:'Plan sonuçları'})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Sonuç CSV',exact:true})).toHaveCount(0);
  await advanced(page);
  await page.getByLabel('Elle sıra (virgülle ayrılmış borular)',{exact:true}).fill('233, 247, 137');
  const after=await calculate(page);
  expect(after.id).not.toBe(before.id);
  expect(after.result.input_sha256).not.toBe(before.result.input_sha256);
  expect(after.result.input.crews).toBe(1);
  expect(after.result.methods.manual.assignments.map((a:any)=>a.pipe_id)).toEqual(['233','247','137']);
  expect(after.result.methods.fifo.metrics.repair_completion_hour).toBe(11);
  await expect(page.getByRole('button',{name:'Elle belirlenen sıra',exact:true})).toBeVisible();
});

test('boş ve bozuk senaryo, geçersiz ekip ve gerçek çözücü başarısızlığı',async({page})=>{
  await example(page);await advanced(page);
  const file=page.getByLabel('Senaryo JSON dosyası',{exact:true});
  for(const buffer of [Buffer.alloc(0),Buffer.from('{broken')]){
    await file.setInputFiles({name:'bozuk.json',mimeType:'application/json',buffer});
    await expect(page.getByRole('alert')).toContainText('Senaryo dosyası okunamadı');
  }
  await file.setInputFiles(path.join(root,'experiments/configs/example.json'));
  await page.getByLabel('Ekip sayısı',{exact:true}).fill('0');
  await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Ekip sayısı');
  await page.getByLabel('Ekip sayısı',{exact:true}).fill('2');
  await page.getByLabel('Yakınsama deneme sınırı',{exact:true}).fill('1');
  await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('EPANET',{timeout:95000});
  await expect(page.getByRole('status')).toContainText('Sonuç üretilemedi');
  await expect(page.getByRole('region',{name:'Plan sonuçları'})).toHaveCount(0);
});

test('klavye ile şemadan seçim ve Türkçe yöntem yardımı',async({page})=>{
  const first=page.locator('[data-pipe]').first();
  await first.focus();await first.press('Enter');
  await expect(first).toHaveAttribute('aria-pressed','true');
  await first.press('ArrowRight');
  await page.keyboard.press('Enter');
  await expect(page.locator('.faults>li')).toHaveCount(2);
  await page.getByRole('button',{name:'Örnek senaryo yükle',exact:true}).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.faults>li')).toHaveCount(3);
  await page.getByRole('link',{name:'Veri ve yöntem',exact:true}).click();
  await expect(page.locator('#method')).toContainText('İzolasyon kaçak fiziği değildir');
  await expect(page.locator('footer')).toContainText('Öğr. Gör. Enise Odabaş');
  await expect(page.locator('html')).toHaveAttribute('lang','tr');
});

test('BUILD 02 kısa karar özeti eşitliği ve FIFO karşılaştırmasını açıklar',async({page},info)=>{
  await example(page);const {result}=await calculate(page);
  const summary=page.getByRole('region',{name:'Karar özeti',exact:true});
  await expect(summary.locator('.method-verdict')).toContainText('Eşit sonuç');
  await expect(summary).toContainText('137 · 247 · 233');
  await expect(summary.locator('.fifo-comparison')).toContainText(result.methods.fifo.metrics.unmet_demand_volume_m3.toLocaleString('tr-TR',{maximumFractionDigits:2}));
  await expect(summary.locator('.fifo-comparison')).toContainText('bildirim sırasına göredir');
  await expect(summary).toContainText('Müşteri hizmet açığı kaçak su değildir');
  await summary.scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath(`${process.env.SE_IMAGE_PREFIX||'BUILD02_S'}_ozet.png`)});
});

test('BUILD 02 tolerans karşı örneği gizlenmeden gösterilir',async({page})=>{
  const protocol=JSON.parse(await fs.readFile(path.join(root,'experiments/configs/build02_s_protocol_v1.json'),'utf8'));
  const scenario=protocol.cases.find((c:any)=>c.case_id==='T11_C2').scenario;
  await advanced(page);
  await page.getByLabel('Senaryo JSON dosyası',{exact:true}).setInputFiles({name:'T11_C2.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(scenario))});
  const {result}=await calculate(page);
  expect(result.methods.proposal.metrics.repair_completion_hour).toBe(8);
  expect(result.methods.manual.metrics.repair_completion_hour).toBe(7);
  await expect(page.locator('.numerical-warning')).toContainText('Sayısal eşitlik uyarısı');
  await expect(page.locator('.numerical-warning')).toContainText('garantisi verilmez');
});
