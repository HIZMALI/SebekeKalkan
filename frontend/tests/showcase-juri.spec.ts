import {expect, test} from '@playwright/test';
import {readFile} from 'node:fs/promises';

const sizes = [[390, 844], [768, 1024], [1280, 720], [1366, 768], [1920, 1080]];

test('şema ve 08.00 karşılaştırması beş ilk ekrana sığar', async({page})=>{
  const errors: string[] = [];
  page.on('pageerror', error=>errors.push(error.message));
  for(const [width, height] of sizes){
    await page.setViewportSize({width, height});
    await page.goto('/demo/');
    await expect(page.getByTestId('instant-difference')).toHaveText('+2,06 L/s');
    for(const item of [page.locator('.v4-network'), page.getByTestId('demand-greedy'), page.getByTestId('demand-s02_b6')]){
      await expect(item).toBeInViewport({ratio: .98});
    }
    await expect(page.getByTestId('main-gain')).toHaveText('%4,77');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
  }
  expect(errors).toEqual([]);
});

test('yöntem değişirken geometri sabit kalır, boru ve basınç gerçek adımı izler', async({page})=>{
  await page.goto('/demo/');
  const map = page.locator('.v4-network');
  const geometry = await map.getAttribute('viewBox');
  const pipe = map.locator('[data-pipe="12"]');
  const inspect = page.getByTestId('pipe-inspector');
  await map.getByRole('button',{name:'Boru 12',exact:true}).press('Enter');
  await expect(inspect).toContainText('Onarıldı · açık');
  await expect(inspect).toContainText('02.00–07.00');
  await expect(pipe).toHaveAttribute('data-kind', 'repaired');
  await expect(map.locator('[data-node="9"]')).toHaveClass('full');
  await page.getByRole('button',{name:'Güçlü referans',exact:true}).click();
  await expect(map).toHaveAttribute('viewBox', geometry!);
  await expect(inspect).toContainText('Onarım sürüyor · kapalı');
  await expect(inspect).toContainText('05.00–10.00');
  await expect(pipe).toHaveAttribute('data-kind', 'work');
  await expect(map.locator('[data-node="9"]')).toHaveClass('low');
  await page.getByRole('button',{name:'02.00',exact:true}).click();
  await expect(map.locator('[data-kind="fault"], [data-kind="work"]')).toHaveCount(4);
  await expect(page.locator('.gantt-cursor').first()).toHaveCSS('left', /px$/);
  await expect(page.locator('.gantt-row--greedy [data-repair-status="active"]')).toHaveAttribute('data-pipe-id', '9');
  await page.getByRole('button',{name:'Son onarım'}).click();
  await expect(page.getByTestId('time-label')).toHaveText('16.00');
  await expect(map.locator('.repair-tick')).toHaveCount(4);
  await expect(page.getByTestId('demand-greedy')).toHaveText('0,00 L/s');
  await expect(page.getByText('Kayıtta iki plan da 6,31 L/s talebi karşılayamıyor.')).toBeVisible();
  await expect(page.locator('[data-repair-status="completed"]')).toHaveCount(8);
  await page.getByRole('button',{name:'Başlangıca dön'}).click();
  await expect(map.locator('[data-kind="pending"]')).toHaveCount(4);
});

test('yakınlaştırma, kamera sıfırlama ve kayıtlı zaman adımlarını oynatma', async({page})=>{
  await page.goto('/demo/');
  const map = page.locator('.v4-network');
  const geometry = await map.getAttribute('viewBox');
  await expect(page.getByRole('button',{name:'Uzaklaştır'})).toBeDisabled();
  await page.getByRole('button',{name:'Yakınlaştır'}).click();
  await expect(map).toHaveAttribute('data-zoom', '1.3');
  await expect(map).not.toHaveAttribute('viewBox', geometry!);
  await page.getByRole('button',{name:'Sıfırla'}).click();
  await expect(map).toHaveAttribute('viewBox', geometry!);
  const time = page.getByRole('slider',{name:'Simülasyon zamanı'});
  await time.press('ArrowRight');
  await expect(page.getByTestId('time-label')).toHaveText('08.15');
  await expect(page.locator('.schedule-time')).toContainText('08.15');
  await page.getByLabel('Oynatma hızı').selectOption('4');
  await page.getByRole('button',{name:'Zamanı oynat'}).click();
  await expect.poll(async()=>Number(await time.inputValue())).toBeGreaterThan(33);
  await page.getByRole('button',{name:'Zamanı duraklat'}).click();
  await expect(page.getByRole('button',{name:'Zamanı oynat'})).toBeVisible();
  const stopped = await time.inputValue();
  // Longer than two ticks at the selected speed.
  await new Promise(resolve=>setTimeout(resolve, 240));
  await expect(time).toHaveValue(stopped);
});

test('gerçek tam ekran, kısayollar ve Escape ile odak geri dönüşü', async({page})=>{
  await page.setViewportSize({width:1280,height:720});
  await page.goto('/demo/');
  await page.getByRole('button',{name:'Jüri modu',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>document.fullscreenElement?.id)).toBe('gosterim');
  await expect(page.getByRole('navigation')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Onarım çizelgesi'})).toBeVisible();
  await expect(page.locator('.gantt')).toBeInViewport({ratio: .98});
  await expect(page.getByRole('slider',{name:'Simülasyon zamanı'})).toBeInViewport();
  await page.keyboard.press('2');
  await expect(page.getByTestId('time-label')).toHaveText('02.00');
  await page.keyboard.press('8');
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByTestId('time-label')).toHaveText('07.45');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Jüri modu',exact:true})).toBeFocused();
  expect(await page.evaluate(()=>document.fullscreenElement)).toBeNull();
});

test('tarayıcı tam ekranı reddederse odak görünümü ve çıkış çalışır', async({page})=>{
  await page.addInitScript(()=>{
    Element.prototype.requestFullscreen = ()=>Promise.reject(new DOMException('Tam ekran engellendi', 'NotAllowedError'));
  });
  await page.goto('/demo/');
  await page.getByRole('button',{name:'Jüri modu',exact:true}).click();
  await expect(page.locator('#gosterim')).toHaveAttribute('data-jury', 'true');
  expect(await page.evaluate(()=>document.fullscreenElement)).toBeNull();
  await page.getByRole('button',{name:'02.00',exact:true}).click();
  await expect(page.getByTestId('time-label')).toHaveText('02.00');
  await page.getByRole('button',{name:'Jüri modundan çık'}).click();
  await expect(page.getByRole('heading',{level:1})).toBeVisible();
});

test('çizelge genişlikleri, indirilen zaman serileri ve JSON donmuş kayda eşit', async({page})=>{
  const rawPath = new URL('../../data/demo/kanit.json', import.meta.url);
  const proof: typeof import('../../data/demo/kanit.json') = JSON.parse(await readFile(rawPath, 'utf8'));
  const {net} = proof;
  await page.goto('/demo/');
  const schedule = page.locator('.gantt');
  for(const plan of ['greedy', 's02_b6'] as const){
    const bars = schedule.locator(`.gantt-row--${plan} li`);
    const data = await bars.evaluateAll(items=>items.map(item=>{
      const bar = item as HTMLLIElement;
      return {id:bar.dataset.pipeId, start:Number(bar.dataset.start), end:Number(bar.dataset.end), size:parseFloat(bar.style.width)};
    }));
    expect(data.map(({id, start, end})=>[id, start, end])).toEqual(net.methods[plan].assignments.map(row=>[row.pipe_id, 60*row.starts_at_h, 60*row.ends_at_h]));
    for(const bar of data) expect(bar.size).toBeCloseTo(100*(bar.end - bar.start)/1440, 3);
  }
  await page.getByText('Vaka kaynağı ve indirmeler',{exact:true}).click();
  const [csv] = await Promise.all([page.waitForEvent('download'), page.getByRole('button',{name:'Zaman serisi CSV'}).click()]);
  const rows = (await readFile((await csv.path())!, 'utf8')).split('\r\n').slice(1);
  expect(rows).toEqual((['greedy', 's02_b6'] as const).flatMap(plan=>{
    const trace = net.traces[plan];
    return trace.minutes.map((minute, at)=>[net.run, plan, minute, trace.delivered_lps[at], trace.expected_lps[at], trace.deficit_lps[at], trace.raw_sha256].join(';'));
  }));
  const [json] = await Promise.all([page.waitForEvent('download'), page.getByRole('button',{name:'Kanıt JSON'}).click()]);
  expect(JSON.parse(await readFile((await json.path())!, 'utf8'))).toEqual(proof);
});
