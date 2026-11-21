import {expect, test} from '@playwright/test';
import {readFile} from 'node:fs/promises';

test('üç hazır girdi düzenlenebilir ve yüklemek hesap başlatmaz', async({page})=>{
  const presets: typeof import('../src/final-v4/presets.json') =
    JSON.parse(await readFile(new URL('../src/final-v4/presets.json',import.meta.url),'utf8'));
  let started=0;
  page.on('request',r=>{
    if(r.method()==='POST'&&r.url().endsWith('/api/final/v2/custom/jobs'))started++;
  });
  await page.goto('/final-v4/senaryo');
  const chooser=page.getByRole('region',{name:'Hazır senaryolar'});
  for(const {title,request} of presets) {
    const preset=chooser.getByRole('button',{name:title,exact:true});
    await preset.click();
    await expect(preset).toHaveAttribute('aria-pressed','true');
    await expect(page.getByLabel('Örnek şebeke')).toHaveValue(request.network);
    await expect(page.getByLabel('Ekip sayısı')).toHaveValue(String(request.crews));
    await expect(page.getByRole('button',{name:'Canlı hesapla'})).toBeEnabled();
    for(const fault of request.faults) {
      await expect(page.getByLabel('Boru '+fault.pipe_id+' onarım süresi')).toHaveValue(String(fault.repair_hours));
    }
    if(request.faults.length===4){
      await expect(page.getByLabel(request.search==='fast'?'Hızlı · B6 / 6 aday':'Kapsamlı · 24 sıra')).toBeChecked();
    }
    const first=request.faults[0];
    await page.getByLabel('Boru '+first.pipe_id+' onarım süresi').selectOption(first.repair_hours===2?'3':'2');
    await expect(preset).toHaveAttribute('aria-pressed','false');
    await expect(page.getByRole('button',{name:'CSV indir'})).toHaveCount(0);
  }
  expect(started).toBe(0);
});

test('oranın kapsamı ve bilimsel sınırlar varsayılan görünümde açık', async({page})=>{
  await page.goto('/final-v4');
  const decision=page.locator('.v4-decision');
  await expect(decision).toContainText('Net2_G4_C1 · Net2 iç değerlendirme');
  await expect(decision).toContainText('%4,77');
  await expect(decision).toContainText('Saha su tasarrufu ölçülmedi');
  await expect(page.getByText(/Model şeması coğrafi harita değildir/)).toBeVisible();
  const scope=page.locator('.v4-science-scope');
  for(const phrase of ['0/6 kazanım','24 tam sayım yalnız beklemesiz','Makine öğrenmesi','B6 aday havuzunda FIFO ve güçlü referans']){
    await expect(scope).toContainText(phrase);
  }
  await page.getByRole('button',{name:'Dış ağ · Skeletonize'}).click();
  await expect(decision).toContainText('Eşit');
  await expect(decision).not.toContainText('%');
});
