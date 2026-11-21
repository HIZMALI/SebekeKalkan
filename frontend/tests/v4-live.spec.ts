import {expect, test} from '@playwright/test';
import type {Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';

const base='/api/final/v2/custom';

async function addFromList(page:Page,id:string) {
  await page.getByLabel('Boru listesi').selectOption(id);
  await page.getByRole('button',{name:'Arıza ekle',exact:true}).click();
}

async function fill(page:Page, desktop:boolean, comprehensive:boolean) {
  await page.goto('/final-v4/senaryo');
  await expect(page.getByRole('heading',{name:'Onarım senaryonu kur'})).toBeVisible();
  const network=desktop?'Net2':'Skeletonize';
  await page.getByLabel('Örnek şebeke').selectOption(network);
  const ids=desktop?['17','9','18','38']:['54','11','64'];
  const hours=desktop?[3,2,5,4]:[2,4,3];
  const map=page.getByRole('group',{name:network+' şebeke şeması. Ok tuşlarıyla kaydırın.',exact:true});
  await expect(map).toBeVisible();
  if(desktop){
    const line=map.getByRole('button',{name:'Boru '+ids[0],exact:true});
    const at=await line.evaluate((edge:SVGGeometryElement)=>{
      const p=edge.getPointAtLength(edge.getTotalLength()*.45).matrixTransform(edge.getScreenCTM()!);
      return {x:p.x,y:p.y};
    });
    await page.mouse.click(at.x,at.y);
    await expect(line).toHaveAttribute('aria-pressed','true');
    await map.getByRole('button',{name:'Boru '+ids[1],exact:true}).press('Space');
    await expect(map.getByRole('button',{name:'Boru '+ids[1],exact:true})).toHaveAttribute('aria-pressed','true');
    for(const id of ids.slice(2))await addFromList(page,id);
  }else{
    for(const id of ids)await addFromList(page,id);
  }
  await page.getByLabel('Ekip sayısı').selectOption('2');
  for(const [i,id] of ids.entries())await page.getByLabel('Boru '+id+' onarım süresi').selectOption(String(hours[i]));
  if(comprehensive)await page.getByLabel('Kapsamlı · 24 sıra').check();
  return {network,crews:2,search:comprehensive?'comprehensive':'fast',
    faults:ids.map((id,i)=>({pipe_id:id,repair_hours:hours[i]}))};
}

test('gerçek yeni senaryo, basınç görünümü ve dosyalar', async({page,request},info)=>{
  const desktop=info.project.name==='edge-desktop';
  if(desktop)await page.setViewportSize({width:1920,height:1080});
  const errors:string[]=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const input=await fill(page,desktop,desktop);
  await page.screenshot({path:info.outputPath('04-kullanici-girdisi.png'),fullPage:true});
  const [response]=await Promise.all([
    page.waitForResponse(r=>r.url().endsWith(base+'/jobs')&&r.request().method()==='POST'),
    page.getByRole('button',{name:'Canlı hesapla',exact:true}).click(),
  ]);
  expect(response.status()).toBe(202);
  const queued=await response.json();
  expect(queued.mode).toBe('LIVE_USER_SCENARIO');
  expect(queued.request).toEqual(input);
  expect(queued.timeout_seconds).toBe(180);
  expect(queued.job_id).toMatch(/^[a-f0-9]{32}$/);
  expect(queued.job_id).not.toBe('efef66dd0e384da19b9dfaac2ca3445a');
  const job=base+'/jobs/'+queued.job_id;
  const queuedView=await request.get(job+'/view');
  expect(queuedView.status()).toBe(409);
  await expect(page.getByRole('button',{name:'CSV indir'})).toHaveCount(0);
  const status=page.locator('#v4-live-status');
  await expect(status.getByRole('status')).toContainText('Fizik kabulü tamamlandı',{timeout:105000});
  await expect(page.getByRole('heading',{name:'Arama kapsamı ve maliyet'})).toBeVisible({timeout:15000});
  const finished=await (await request.get(job)).json();
  expect(finished.worker_exit_code).toBe(0);
  expect(finished.input_sha256).toBe(queued.input_sha256);
  expect(finished.result.wntr_calls).toBe(2*finished.result.trial_count);
  expect(finished.elapsed_seconds).toBeLessThan(180);
  if(desktop) {
    expect(finished.result.coverage.complete_orders).toBe(24);
    expect(finished.result.coverage.unique_schedules).toBeLessThan(24);
    await expect(page.locator('[aria-label="Arama kapsamı ve maliyet"]')).toContainText('24 önceliğin tamamını çözdü');
  } else {
    expect(finished.method_version).toBe('decision_policy_v2');
    expect(finished.result.coverage.total_priorities).toBe(6);
  }
  await expect(page.getByRole('slider',{name:'Zaman'})).toHaveAttribute('aria-valuetext','02:00');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  for(const ext of ['csv','json','pdf']){
    const [download]=await Promise.all([page.waitForEvent('download'),
      status.getByRole('button',{name:ext.toUpperCase()+' indir'}).click()]);
    const target=info.outputPath('canli.'+ext);
    await download.saveAs(target);
    const bytes=await readFile(target);
    if(ext==='json')expect(JSON.parse(bytes.toString())).toEqual(finished);
    if(ext==='pdf')expect(bytes.subarray(0,5).toString()).toBe('%PDF-');
    if(ext==='csv')expect(bytes.toString()).toContain(queued.job_id);
  }
  await page.locator('.v4-work-grid').scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath('05-kullanici-sonuc.png')});
  await page.reload();
  await expect(page.getByRole('slider',{name:'Zaman'})).toBeVisible();
  await expect(page.getByLabel('Ekip sayısı')).toHaveValue('2');
  expect(errors).toEqual([]);
});

test('iptal ve aynı anda ikinci iş kapıları',async({page,request},info)=>{
  const desktop=info.project.name==='edge-desktop';
  const input=await fill(page,desktop,false);
  const [response]=await Promise.all([page.waitForResponse(r=>r.url().endsWith(base+'/jobs')&&r.request().method()==='POST'),
    page.getByRole('button',{name:'Canlı hesapla'}).click()]);
  const queued=await response.json();
  expect(response.status()).toBe(202);
  const second=await request.post(base+'/jobs',{data:input});
  expect(second.status()).toBe(429);
  await page.getByRole('button',{name:'İşi iptal et'}).click();
  await expect(page.locator('#v4-live-status').getByRole('status')).toContainText('İptal edildi',{timeout:18000});
  await expect(page.getByRole('button',{name:'CSV indir'})).toHaveCount(0);
  for(const ext of ['csv','json','pdf'])expect((await request.get(base+'/jobs/'+queued.job_id+'/export/'+ext)).status()).toBe(409);
  await page.screenshot({path:info.outputPath('06-iptal.png')});
});
