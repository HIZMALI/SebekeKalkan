import {test,expect,Page} from '@playwright/test';
import fs from 'node:fs/promises';
// v2 can spend 180 seconds on a valid solve, before polling and downloads.
test.describe.configure({ timeout: 210000 });
async function sample(page:Page){await page.getByRole('button',{name:'Örnek senaryo yükle',exact:true}).click();await expect(page.locator('.faults>li')).toHaveCount(3);}
async function calculate(page:Page){const q=page.waitForResponse(r=>r.url().endsWith('/api/v2/experiments')&&r.request().method()==='POST');await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();const response=await q;expect(response.status()).toBe(202);const id=(await response.json()).id;await expect(page.getByRole('region',{name:'Plan sonuçları',exact:true})).toBeVisible({timeout:185000});const r=await page.request.get('/api/v2/experiments/'+id);return{id,result:(await r.json()).result};}
test.beforeEach(async({page})=>{await page.goto('/');});
test('MASTER varsayılan WNTR v2 fizik kapısı ve T11 yedi saat',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await sample(page);const {id,result:r}=await calculate(page);
  expect(r.model_version).toBe('SK-WNTR-v2.0');expect(r.decision.selected.order).toEqual(['153','193','112']);expect(r.methods.proposal.metrics.repair_completion_hour).toBe(7);expect(r.physical_validation.pass).toBe(true);
  await expect(page.getByTestId('physical-status')).toContainText('Fiziksel doğrulama geçti');await expect(page.locator('.numerical-warning')).toHaveCount(0);
  for(const name of ['Deney JSON','Sonuç CSV','PDF raporu']){const w=page.waitForEvent('download');await page.getByRole('link',{name,exact:true}).click();const bytes=await fs.readFile((await (await w).path())!);expect(bytes.length).toBeGreaterThan(100);if(name==='PDF raporu')expect(bytes.subarray(0,5).toString()).toBe('%PDF-');if(name==='Deney JSON')expect(JSON.parse(bytes.toString('utf-8')).model_version).toBe(r.model_version);}
  await page.getByLabel('Zaman adımı',{exact:true}).fill('8');await expect(page.getByText('2. saat',{exact:true})).toBeVisible();
  await page.screenshot({path:info.outputPath('MASTER_tam.png'),fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();expect(errors).toEqual([]);
});
test('MASTER WNTR gerçek yakınsama hatası olumlu sonuç göstermez',async({page})=>{
  await sample(page);await page.getByText('Yöntem ayarları ve elle sıra',{exact:true}).click();await page.getByLabel('Yakınsama deneme sınırı',{exact:true}).fill('1');await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();await expect(page.getByRole('alert')).toContainText('WNTR',{timeout:60000});await expect(page.getByRole('region',{name:'Plan sonuçları',exact:true})).toHaveCount(0);await expect(page.getByRole('link',{name:'Deney JSON',exact:true})).toHaveCount(0);
});
test('MASTER gerçek hesaplamayı iptal et ve eski sonucu gizle',async({page})=>{
  await sample(page);await page.getByRole('button',{name:'Planları hesapla',exact:true}).click();await page.getByRole('button',{name:'Hesaplamayı iptal et',exact:true}).click();await expect(page.getByRole('alert')).toContainText('iptal',{timeout:20000});await expect(page.getByRole('region',{name:'Plan sonuçları',exact:true})).toHaveCount(0);
});
