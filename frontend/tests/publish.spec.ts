import {expect, test} from '@playwright/test';
import path from 'node:path';

test('dosya doğrulanırken düzenleme bekler, sonraki ekip girdisi kaybolmaz', async ({page})=>{
  let release=()=>{};
  const pending=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/v2/scenario/validate',async route=>{
    const response=await route.fetch();
    await pending;
    await route.fulfill({response});
  });
  try{
    await page.goto('/');
    await page.getByText('Yöntem ayarları ve elle sıra',{exact:true}).click();
    const file=page.getByLabel('Senaryo JSON dosyası',{exact:true});
    const crews=page.getByLabel('Ekip sayısı',{exact:true});
    await file.setInputFiles(path.resolve('../experiments/configs/example.json'));
    await expect(crews).toBeDisabled();
    await expect(page.getByRole('button',{name:'Planları hesapla'})).toBeDisabled();
    release();
    await expect(page.getByRole('status')).toContainText('Senaryo dosyası doğrulandı');
    await crews.fill('0');
    const pendingResponse=page.waitForResponse(r=>r.url().endsWith('/api/v2/experiments')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Planları hesapla'}).click();
    expect((await pendingResponse).status()).toBe(422);
    await expect(crews).toHaveValue('0');
    await expect(page.getByRole('alert')).toContainText('Ekip sayısı');
  }finally{release();}
});

test('sıfır girişle doğrulanmış şema, aynı saatte yöntem değişimi ve gerçek CSV', async ({page})=>{
  await page.goto('/demo/');
  await expect(page.getByRole('heading',{level:1})).toContainText('Su şebekesinde önce hangi arızaya');
  await expect(page.getByTestId('main-gain')).toHaveText('%4,77');
  await expect(page.locator('[data-mode]')).toHaveAttribute('data-mode','recorded_verified');
  await expect(page.locator('[data-kind]')).toHaveCount(4);
  await page.getByRole('button',{name:'02.00',exact:true}).click();
  await expect(page.getByTestId('time-label')).toHaveText('02.00');
  await page.getByRole('button',{name:'08.00',exact:true}).click();
  await page.getByRole('button',{name:'Güçlü referans'}).click();
  await expect(page.getByRole('button',{name:'Güçlü referans'})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByTestId('time-label')).toHaveText('08.00');
  await expect(page.getByText('8,97 L/s')).toBeVisible();
  await expect(page.getByText('11,03 L/s')).toBeVisible();
  await page.getByText('Vaka kaynağı ve indirmeler',{exact:true}).click();
  const [file]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Zaman serisi CSV'}).click()]);
  expect((await file.path())?.length).toBeGreaterThan(0);
  await page.getByText('Araştırmanın kapsamı ve tüm sonuçlar',{exact:true}).click();
  await expect(page.getByText(/23 birincil kıyasta 3 kazanım, 20 eşitlik/)).toBeVisible();
  await expect(page.getByRole('link',{name:'Yerel WNTR moduna geç'})).toHaveAttribute('href','/final-v4/senaryo');
  const dimensions=await page.evaluate(()=>[window.innerWidth,document.documentElement.scrollWidth]);
  expect(dimensions[1]).toBe(dimensions[0]);
});
