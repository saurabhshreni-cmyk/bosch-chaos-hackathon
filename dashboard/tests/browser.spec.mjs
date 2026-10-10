import { test, expect } from '@playwright/test';

for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  test(`dashboard evidence and controls ${viewport.width}px`,async({page})=>{
    await page.setViewportSize(viewport);
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
    await page.goto('/');
    await expect(page.locator('#session-label')).toContainText('Session');
    await page.locator('#live').uncheck();
    const choices=await page.locator('#mobile-session option').evaluateAll(options=>options.map(option=>option.value));
    const retained='20261010T101001857Z';
    if(choices.includes(retained)){
      if(viewport.width<650)await page.locator('#mobile-session').selectOption(retained);
      else await page.locator(`[data-session="${retained}"]`).click();
      await expect(page.locator('#session-label')).toContainText(retained);
    }
    await expect(page.locator('#latency-chart')).toBeVisible();
    expect(await page.locator('#latency-chart').evaluate(canvas=>{
      const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
      let colored=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]<150&&pixels[i+3]>0)colored++;return colored;
    })).toBeGreaterThan(200);
    expect(await page.locator('.brand img').evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
    await page.screenshot({path:`test-results/overview-${viewport.width}.png`,fullPage:true});
    await page.locator('[data-tab=dependencies]').click();
    await expect(page.locator('#dependency-graph')).toBeVisible();
    expect(await page.locator('#dependency-graph').evaluate(canvas=>canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some(value=>value>0))).toBe(true);
    await page.screenshot({path:`test-results/dependencies-${viewport.width}.png`,fullPage:true});
    await page.locator('[data-tab=evidence]').click();
    await expect(page.locator('#view')).toContainText('Ranked AI findings');
    if(choices.includes(retained))await expect(page.locator('.finding')).toHaveCount(2);
    await page.screenshot({path:`test-results/evidence-${viewport.width}.png`,fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
    expect(overflow).toBe(false);
    await page.locator('[data-tab=overview]').click();
    if(await page.locator('#execute').isEnabled()){
      await page.locator('#execute').click();await expect(page.locator('#confirm')).toBeVisible();
      await expect(page.locator('#confirm-run')).toBeDisabled();
      await page.locator('#sandbox-confirm').check();await expect(page.locator('#confirm-run')).toBeEnabled();
      await page.locator('#confirm button[value=cancel]').click();
    }
    expect(errors).toEqual([]);
  });
}

test('empty history remains usable',async({page,request})=>{
  const snapshot=await (await request.get('/api/state')).json();
  await page.route('**/api/state*',route=>route.fulfill({json:{...snapshot,sessions:[],selected:null,job:null,locks:{Agent:false,Experiment:false,error:null}}}));
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('#session-label')).toHaveText('No session selected');
  await page.locator('[data-tab=dependencies]').click();
  await expect(page.locator('#dependency-graph')).toBeVisible();
  expect(errors).toEqual([]);
});

test('real preview streams progress without injecting faults',async({page})=>{
  test.setTimeout(60000);
  test.skip(process.env.RUN_AGENT_TEST!=='1','Opt in only with the local app running.');
  await page.goto('/');
  await page.getByText('Fixed order',{exact:true}).click();
  await page.locator('#baseline').fill('10');
  await page.locator('#budget').fill('1');
  for(const id of ['database-crash','rabbitmq-crash','workshop-delay'])await page.locator(`input[name=experiment][value="${id}"]`).uncheck();
  await expect(page.locator('#preview')).toBeEnabled();
  await page.locator('#preview').click();
  await expect(page.locator('#view')).toContainText('recorded probes',{timeout:20000});
  await expect(page.locator('#status-line')).toContainText('Plans only; no faults injected',{timeout:25000});
  await expect(page.locator('#view')).toContainText('Plan validated');
  const selected=await page.evaluate(async()=>{
    const id=document.querySelector('#session-label').textContent.split(' ')[1];
    return (await (await fetch(`/api/state?session=${id}`)).json()).selected;
  });
  expect(selected.Execute).toBe(false);
  expect(selected.experiments).toHaveLength(0);
  expect(selected.baseline.Healthy).toBe(true);
  expect(selected.liveBaseline.Samples.length).toBeGreaterThan(0);
  await page.screenshot({path:'test-results/preview-live.png',fullPage:true});
});
