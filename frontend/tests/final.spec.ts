import {expect, test} from '@playwright/test';
import type {Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';

const broken = '/api/final/v1/cases/Net2_G4_C1';
const open = async (page:Page, id:string) => {
  await page.getByRole('button', {name:'Vakayı aç '+id}).click();
  await expect(page.locator('#active-case')).toBeVisible();
};

test('kayıtlı Net2 ana akışı, gerçek şema ve çıktı', async ({page}, info) => {
  const errors:string[]=[];
  const external:string[]=[];
  const origin=new URL(info.project.use.baseURL!).origin;
  await page.route('**/*', route => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    external.push(route.request().url());
    return route.abort();
  });
  page.on('console', msg=>{if(msg.type()==='error')errors.push(msg.text());});
  page.on('pageerror', err=>errors.push(String(err)));
  page.on('requestfailed', r=>errors.push(r.url()));
  page.on('response', r=>{if(r.status()>=400&&r.url().includes('/api/')) errors.push(r.url());});
  await page.goto('/final');
  await expect(page.locator('.fd-cards article button')).toHaveCount(7);
  await page.screenshot({path:info.outputPath('01-katalog.png'),fullPage:true});
  await open(page,'Net2_G4_C1');
  const story=page.locator('.fd-story');
  await expect(story).toContainText('1.509,015623');
  await expect(story).toContainText('1.437,028326');
  await expect(story).toContainText('71,987297');
  await expect(story).toContainText('% 4,77');
  await expect(page.locator('#comparison')).toContainText('34,5');
  await expect(page.locator('#comparison')).toContainText('31,5');
  await expect(page.locator('.fd-timeline')).toContainText('başlangıcı 2. saat');
  await expect(page.locator('.fd-timeline').getByText('Bitiş 16. saat')).toHaveCount(3);
  const map=page.locator('svg.fd-map');
  await expect(map).toBeVisible();
  await expect(map.locator('polyline title')).toHaveCount(4);
  await expect(page.locator('.fd-order')).toContainText('12 → 9 → 17 → 18');
  const initial=await map.getAttribute('viewBox');
  await page.getByRole('button',{name:'Yakınlaştır'}).click();
  await expect(map).not.toHaveAttribute('viewBox',initial!);
  await map.focus();
  await page.keyboard.press('ArrowRight');
  await page.getByRole('button',{name:'Sıfırla'}).click();
  await expect(map).toHaveAttribute('viewBox',initial!);
  await page.getByLabel('Şema ve hizmet grafiği').selectOption('greedy');
  await expect(page.locator('.fd-order')).toContainText('9 → 12 → 18 → 17');
  await page.getByLabel('Şema ve hizmet grafiği').selectOption('s02_b6');
  const chart=page.locator('#comparison');
  for (const ext of ['SVG','PNG','Kanıt JSON']) {
    const [download]=await Promise.all([page.waitForEvent('download'),chart.getByRole('button',{name:ext+' indir'}).click()]);
    const target=info.outputPath(download.suggestedFilename());
    await download.saveAs(target);
    const bytes=await readFile(target);
    if(ext==='SVG')expect(bytes.toString()).toContain('1.437,028326');
    if(ext==='PNG')expect(bytes.subarray(0,8).toString('hex')).toBe('89504e470d0a1a0a');
    if(ext==='Kanıt JSON')expect(JSON.parse(bytes.toString()).evidence.record_id).toBe('efef66dd0e384da19b9dfaac2ca3445a');
  }
  await page.locator('.fd-story').getByRole('link',{name:'Kaynağı incele'}).click();
  await page.getByText('Fizik kapıları, kayıt kimliği ve SHA-256').click();
  await expect(page.locator('#proof')).toContainText('Fizik kapıları geçti');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('02-net2-kanit.png'),fullPage:true});
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('bildirim sırası, dış ağ eşitliği ve tarihsel kaynak kapsamı', async ({page},info)=>{
  await page.goto('/final');
  await open(page,'Net2_S3_C1');
  await expect(page.locator('.fd-story')).toContainText('696,268565');
  await expect(page.locator('.fd-story')).toContainText('416,235811');
  await expect(page.getByText('Güçlü tekli etkiye karşı kazanç sıfır.')).toBeVisible();
  await page.screenshot({path:info.outputPath('03-bildirim-sirasi.png'),fullPage:true});
  await open(page,'Skeletonize_G1_C1');
  await expect(page.locator('.fd-story')).toContainText('16,602816');
  await expect(page.locator('.fd-story')).toContainText('aynı sırayı verdi');
  await expect(page.locator('#research')).toContainText('0 kazanım / 6 eşitlik / 0 kayıp');
  await expect(page.locator('#research')).toContainText('4 kazanım / 10 eşitlik / 0 kayıp');
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#research').getByRole('button',{name:'SVG indir'}).click()]);
  await download.saveAs(info.outputPath('Sprint02-karsilastirma.svg'));
  const [png]=await Promise.all([page.waitForEvent('download'),page.locator('#research').getByRole('button',{name:'PNG indir'}).click()]);
  await png.saveAs(info.outputPath('Sprint02-karsilastirma.png'));
  await page.screenshot({path:info.outputPath('04-dis-ag.png'),fullPage:true});
  await open(page,'Net3_A1_C1');
  await expect(page.getByText('Çizelge detayı mevcut değil.')).toBeVisible();
  await expect(page.getByText('Bu kayıtta ham zaman serisi bulunmuyor.',{exact:false})).toBeVisible();
});

test('jüri görünümü, klavye ve Escape', async ({page},info)=>{
  const sizes=info.project.name==='edge-desktop'?[{width:1366,height:900},{width:1920,height:1080}]:[{width:390,height:844}];
  for(const size of sizes){
    await page.setViewportSize(size);
    await page.goto('/final');
    const start=page.getByRole('button',{name:'Gösterimi başlat'});
    await start.focus();
    await page.keyboard.press('Enter');
    const dialog=page.getByRole('dialog',{name:'Jüri sunumu'});
    await expect(dialog.getByRole('heading',{name:'Dört arızada daha az hizmet açığı'})).toBeVisible();
    await expect(dialog.getByRole('button',{name:'Dış ağ'})).toBeVisible();
    if(info.project.name==='edge-desktop')await expect.poll(()=>page.evaluate(()=>Boolean(document.fullscreenElement))).toBe(true);
    await page.screenshot({path:info.outputPath(`05-sunum-${size.width}.png`)});
    await dialog.getByRole('button',{name:'Dış ağ'}).click();
    await expect(dialog.getByRole('heading',{name:'Başka ağdaki eşitlik'})).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect.poll(()=>page.evaluate(()=>Boolean(document.fullscreenElement))).toBe(false);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('kanıt hatası sayıları ve indirmeyi kapatır', async ({page})=>{
  await page.route('**'+broken, r=>r.fulfill({status:409,json:{message:'Kaynak doğrulanamadı.'}}));
  await page.goto('/final');
  await page.getByRole('button',{name:'Vakayı aç Net2_G4_C1'}).click();
  await expect(page.getByRole('alert')).toContainText('Sayılar ve dışa aktarma kapatıldı');
  await expect(page.locator('#comparison')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Vakayı aç Net2_G4_C1'})).toHaveCount(0);
});

test('yeni dört arıza canlı işi ve doğrulanmış üç çıktı', async ({page,request},info)=>{
  const base='/api/final/v1/live';
  const locked=await (await request.get(base+'/scenarios')).json();
  expect(locked.scenarios).toHaveLength(14);
  const rejected=await request.post(base+'/jobs',{data:{case_id:'Net3_A1_C1'}});
  expect(rejected.status()).toBe(422);
  expect((await request.post(base+'/jobs',{data:{case_id:'Net2_G4_C1',path:'secret.inp'}})).status()).toBe(422);
  const caseId=info.project.name==='edge-desktop'?'Net2_G4_C1':'Skeletonize_G1_C1';
  await page.goto('/final');
  const section=page.locator('#four-live');
  await section.getByLabel('Kilitli senaryo').selectOption(caseId);
  const queued=page.waitForResponse(r=>r.url().endsWith('/live/jobs')&&r.request().method()==='POST');
  await section.getByRole('button',{name:'Canlı hesapla'}).click();
  const newJob=await (await queued).json();
  const id=newJob.job_id;
  expect(newJob).toMatchObject({status:'queued',case_id:caseId,mode:'live',timeout_seconds:180,method_version:'s02-restoration-1'});
  expect(id).toMatch(/^[a-f0-9]{32}$/);
  const recorded=await (await request.get('/api/final/v1/cases/'+caseId)).json();
  expect(id).not.toBe(recorded.evidence.record_id);
  expect((await request.get(base+'/jobs/'+recorded.evidence.record_id)).status()).toBe(404);
  expect((await request.post(base+'/jobs',{data:{case_id:caseId}})).status()).toBe(429);
  for (const ext of ['csv','json','pdf']) expect((await request.get(base+'/jobs/'+id+'/export/'+ext)).status()).toBe(409);
  await expect(section.getByRole('status')).toContainText('Tamamlandı',{timeout:100000});
  const finished=await (await request.get(base+'/jobs/'+id)).json();
  expect(finished).toMatchObject({job_id:id,worker_exit_code:0,result:{physical_pass:true,job_id:id}});
  expect(finished.elapsed_seconds).toBeLessThan(180);
  expect(finished.input_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(finished.source_sha256).toBe(recorded.evidence.code_sha256);
  expect(finished.result.wntr_calls).toBe(2*finished.result.trial_count);
  for (const method of ['fifo','greedy','s02_b6']) {
    expect(finished.result.methods[method].order).toEqual(recorded.methods[method].order);
    for(const key of Object.keys(recorded.methods[method].metrics)) {
      expect(finished.result.methods[method].metrics[key]).toBeCloseTo(recorded.methods[method].metrics[key], 6);
    }
  }
  await section.getByText('Canlı hesap kimliği ve kaynak').click();
  for(const ext of ['csv','json','pdf']) {
    const [download]=await Promise.all([page.waitForEvent('download'),section.getByRole('link',{name:ext.toUpperCase()+' indir'}).click()]);
    const target=info.outputPath('canli-'+caseId+'.'+ext);
    await download.saveAs(target);
    const bytes=await readFile(target);
    if(ext==='json')expect(JSON.parse(bytes.toString())).toEqual(finished);
    if(ext==='csv'){
      const rows=bytes.toString().trim().split(/\r?\n/);
      const keys=rows.shift()!.replace(/^\uFEFF/,'').split(';');
      for (const row of rows) {
        const cells=row.split(';');
        expect(cells[0]).toBe(id);
        for(const [key,value] of Object.entries(finished.result.methods[cells[4]].metrics)){
          expect(Number(cells[keys.indexOf(key)])).toBe(value);
        }
      }
    }
    if(ext==='pdf')expect(bytes.subarray(0,5).toString()).toBe('%PDF-');
  }
  await section.screenshot({path:info.outputPath('06-canli-'+caseId+'.png')});
});
