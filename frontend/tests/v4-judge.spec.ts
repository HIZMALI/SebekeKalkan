import {expect, test} from '@playwright/test';
import type {Page} from '@playwright/test';

const ready = async (page:Page) => {
  await page.goto('/final-v4');
  await expect(page.getByRole('heading',{name:'Basınç ve onarım',exact:true})).toBeVisible();
};

test('jüri özeti sıfır tıklamada ve üç ekran boyutunda okunur',async({page},info)=>{
  const remote:string[]=[], errors:string[]=[];
  const origin=new URL(info.project.use.baseURL!).origin;
  await page.route('**/*',r=>{
    if(new URL(r.request().url()).origin===origin)return r.continue();
    remote.push(r.request().url());return r.abort();
  });
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text());});
  page.on('requestfailed',request=>errors.push(request.url()));
  const sizes=info.project.name==='edge-desktop'?[{width:1920,height:1080},{width:1366,height:900}]:[{width:390,height:844}];
  for(const size of sizes) {
    await page.setViewportSize(size);
    await ready(page);
    await expect(page.getByRole('heading',{name:'Hangi arızaya önce müdahale edilmeli?'})).toBeVisible();
    const decision=page.locator('.v4-decision');
    await expect(decision).toContainText('%4,77');
    await expect(decision).toContainText('71,99 ağırlıklı m³');
    await expect(decision).toContainText('34,5 → 31,5');
    await expect(decision).toContainText('16 saat = 16 saat');
    await expect(decision.getByRole('list',{name:'Güçlü referans onarım sırası'}).locator('li')).toHaveText(['9','12','18','17']);
    await expect(decision.getByRole('list',{name:'ŞebekeKalkan B6 onarım sırası'}).locator('li')).toHaveText(['12','9','17','18']);
    await expect(page.locator('.v4-network [data-kind]')).toHaveCount(4);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(size.width===1920) {
      const gantt=await page.getByLabel('Ekip zaman çizelgesi').boundingBox();
      expect(gantt!.y+gantt!.height).toBeLessThan(size.height);
      await page.getByRole('button',{name:'Tam ekran',exact:true}).press('Enter');
      await expect.poll(()=>page.evaluate(()=>Boolean(document.fullscreenElement))).toBe(true);
      await page.keyboard.press('Escape');
      await expect.poll(()=>page.evaluate(()=>Boolean(document.fullscreenElement))).toBe(false);
    }
    await page.screenshot({path:info.outputPath(`01-juri-${size.width}.png`)});
    await page.getByText('Bildirim sırasına bak').click();
    await expect(decision.getByRole('list',{name:'Bildirim sırası (FIFO) onarım sırası'}).locator('li'))
      .toHaveText(['17','9','18','12']);
  }
  expect(errors).toEqual([]);
  expect(remote).toEqual([]);
});

test('ham zaman serisiyle basınç, boru, ekip, oynatma ve debi farkı',async({page},info)=>{
  if(info.project.name==='edge-desktop')await page.setViewportSize({width:1920,height:1080});
  await ready(page);
  const slider=page.getByRole('slider',{name:'Zaman'});
  const raw=await (await page.request.get('/api/final/v2/recorded/Net2_G4_C1')).json();
  const trace=raw.traces.s02_b6;
  await expect(slider).toHaveAttribute('aria-valuetext','02:00');
  await expect(page.locator('.v4-frame-pipes li').filter({hasText:'Boru 12'})).toContainText('Ekip 1 onarıyor');
  await expect(page.locator('.v4-service-now strong')).toContainText(new Intl.NumberFormat('tr-TR',{
    minimumFractionDigits:2,maximumFractionDigits:2}).format(trace.delivered_lps[8]));
  await slider.press('ArrowRight');
  await expect(slider).toHaveAttribute('aria-valuetext','02:15');
  await slider.press('Home');
  await expect(page.locator('.v4-network [data-kind=pending]')).toHaveCount(4);
  await slider.press('End');
  await expect(page.locator('.v4-network [data-kind=repaired]')).toHaveCount(4);
  await expect(slider).toHaveAttribute('aria-valuetext','24:00');
  await page.getByLabel('Hız').selectOption('2');
  await page.getByRole('button',{name:'Oynat',exact:true}).click();
  await expect.poll(()=>slider.getAttribute('aria-valuetext')).not.toBe('00:00');
  await page.getByRole('button',{name:'Duraklat',exact:true}).click();
  await expect(page.getByRole('button',{name:'Oynat',exact:true})).toBeVisible();
  await slider.press('Home');
  for(let i=0;i<32;i++)await slider.press('ArrowRight');
  await expect(slider).toHaveAttribute('aria-valuetext','08:00');
  await expect(page.locator('.v4-frame-pipes li').filter({hasText:'Boru 9'})).toContainText('Ekip 1 onarıyor');
  await expect(page.locator('.v4-edges polyline[data-pipe="12"]')).toHaveAttribute('data-kind','repaired');
  const map=page.locator('.v4-network');
  const initial=await map.getAttribute('viewBox');
  await page.getByRole('button',{name:'Yakınlaştır'}).click();
  await expect(map).not.toHaveAttribute('viewBox',initial!);
  const zoomed=await map.getAttribute('viewBox');
  await map.press('ArrowRight');
  await expect(map).not.toHaveAttribute('viewBox',zoomed!);
  await page.getByRole('button',{name:'Sıfırla'}).click();
  await expect(map).toHaveAttribute('viewBox',initial!);
  await page.screenshot({path:info.outputPath('02-basinç-0800.png')});
  await page.getByRole('button',{name:'Güçlü referans',exact:true}).click();
  await expect(page.locator('.v4-frame-pipes li').filter({hasText:'Boru 12'})).toContainText('Ekip 1 onarıyor');
  await page.getByRole('button',{name:'Debi farkı',exact:true}).click();
  await expect(page.locator('[data-curve="reference-minus-proposal"]')).toBeVisible();
  const [svg]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Karşılaştırma SVG'}).click()]);
  await svg.saveAs(info.outputPath('Net2-G4-C1.svg'));
});

test('dış eşitlik ve araştırma bedelleri erişilebilir',async({page},info)=>{
  await ready(page);
  await page.getByRole('button',{name:'Dış ağ · Skeletonize'}).click();
  await expect(page.locator('.v4-main-number')).toContainText('16,60 ağırlıklı m³');
  await expect(page.locator('.v4-main-number')).toContainText('Eşit');
  await expect(page.locator('#v4-science')).toContainText('0 kazanım / 6 eşitlik / 0 kayıp');
  await expect(page.locator('#v4-science')).toContainText('4 kazanım / 10 eşitlik / 0 kayıp');
  await page.getByText('Araştırma kapsamı ve sınırlamalar').click();
  await expect(page.getByText(/898,169174 ağırlıklı/)).toBeVisible();
  await expect(page.getByText(/Net2_G1_C2/).first()).toBeVisible();
  await page.getByText('Yedi kayıt ve tam kaynakları').click();
  await expect(page.locator('.v4-catalog li')).toHaveCount(7);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('03-dis-ag-ve-kanit.png'),fullPage:true});
});

test('hatalı kayıt kartta, animasyonda ve çıktıda ölçüt bırakmaz',async({page})=>{
  await page.route('**/api/final/v2/recorded/Net2_G4_C1',r=>r.fulfill({status:409,
    json:{message:'Kayıt ve ham zaman serisi doğrulanamadı. Ölçüt ve animasyon kapalı.'}}));
  await page.goto('/final-v4');
  await expect(page.getByRole('alert')).toContainText('Ölçüt ve animasyon kapalı');
  await expect(page.locator('.v4-main-number')).toHaveCount(0);
  await expect(page.getByRole('slider',{name:'Zaman'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Ham zaman verisi JSON'})).toHaveCount(0);
});
