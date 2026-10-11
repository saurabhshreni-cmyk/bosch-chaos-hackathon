import { test, expect } from '@playwright/test';

test('automatic discovery separates observed weaknesses and non-executable proposals', async ({ page, request }) => {
  const snapshot = await (await request.get('/api/state')).json();
  const selected = { ...snapshot.selected, DetectOnly: false, AutoDiscover: true, Discovery: { HealthyBaseline: false,
    Findings: [{ Type: 'Observed failure', Subject: 'WorkshopManagement', Summary: 'Two baseline probes failed.', Source: 'Current baseline' }],
    ProposedTests: [{ Name: 'Packet loss', Executable: false, Reason: 'Bounded cleanup tool required.' }], Limitations: 'Proposals are not executable.' } };
  await page.route('**/api/state*', route => route.fulfill({ json: { ...snapshot, selected } }));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page.locator('#auto-discover')).toBeChecked();
    await expect(page.locator('#view')).toContainText('Unhealthy baseline / injection blocked');
    await expect(page.locator('#view')).toContainText('Proposed tests / not executable');
    await expect(page.locator('#view')).toContainText('Two baseline probes failed.');
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  }
});

test('catalog-free detection shows observations without injection plans', async ({ page, request }) => {
  const snapshot = await (await request.get('/api/state')).json();
  const selected = { ...snapshot.selected, DetectOnly: true, Discovery: { Findings: [
    { Type: 'Observed failure', Subject: 'WorkshopManagement', Summary: 'Two baseline probes failed.', Source: 'Current baseline' }
  ] } };
  await page.route('**/api/state*', route => route.fulfill({ json: { ...snapshot, selected } }));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page.locator('#view')).toContainText('Read-only detection / no catalog or injection');
    await expect(page.locator('#view')).toContainText('Two baseline probes failed.');
    await expect(page.locator('#view')).not.toContainText('Selected plans');
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  }
});

test('detection and catalog planning are available together', async ({ page }) => {
  let submitted;
  await page.route('**/api/run', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 400, json: { error: 'Read-only test capture' } });
  });
  await page.goto('/');
  await expect(page.locator('#auto-discover')).toBeChecked();
  for (const checkbox of await page.locator('input[name=experiment]').all()) await checkbox.uncheck();
  await page.locator('#detect').click();
  await expect.poll(() => submitted?.mode).toBe('detect');
  expect(submitted.experiments).toEqual([]);
  expect(submitted.confirmed).toBeUndefined();
  await page.locator('input[value="workshop-crash"]').check();
  await page.locator('#preview').click();
  await expect.poll(() => submitted?.mode).toBe('preview');
  expect(submitted.autoDiscover).toBe(true);
  expect(submitted.experiments).toEqual(['workshop-crash']);
});

test('emergency stop stays available while a run request is pending', async ({ page, request }) => {
  const snapshot = await (await request.get('/api/state')).json();
  await page.route('**/api/state*', route => route.fulfill({ json: {
    ...snapshot, controls: true, stop: false, job: null,
    locks: { Agent: false, Experiment: false, error: null, checked: new Date().toISOString() }
  } }));
  let releaseRun;
  const gate = new Promise(resolve => { releaseRun = resolve; });
  let runStarted = false, stopRequested = false;
  await page.route('**/api/run', async route => {
    runStarted = true;
    await gate;
    await route.fulfill({ status: 400, json: { error: 'Test request released' } });
  });
  await page.route('**/api/stop', async route => {
    stopRequested = true;
    await route.fulfill({ json: { message: 'STOP requested.' } });
  });
  try {
    await page.goto('/');
    await page.locator('#preview').click();
    await expect.poll(() => runStarted).toBe(true);
    await expect(page.locator('#stop')).toBeEnabled();
    await page.locator('#stop').click();
    await expect.poll(() => stopRequested).toBe(true);
  } finally { releaseRun(); }
});

test('multi-agent role status remains readable on desktop and mobile', async ({ page, request }) => {
  const snapshot = await (await request.get('/api/state')).json();
  const selected = { ...snapshot.selected, Stage: 'Recommendation worker running', Error: null,
    Workers: ['Planner', 'Injection', 'Detection', 'Recommendation'].map((Role, index) => ({ Role,
      Status: index === 3 ? 'Running' : 'Completed', ProcessId: 1000 + index, UpdatedUtc: new Date().toISOString(), Error: null })) };
  await page.route('**/api/state*', route => route.fulfill({ json: { ...snapshot, selected } }));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/');
    const workers = page.getByRole('table', { name: 'Agent workers' });
    await expect(workers).toBeVisible();
    await expect(workers).toContainText('Recommendation');
    await expect(workers).toContainText('Running');
    await expect(workers).toContainText('Live detector');
    await expect(workers).toContainText('1003');
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    await page.screenshot({ path: `test-results/workers-${width}.png`, fullPage: true });
  }
});

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

for (const width of [1440,390]) {
  test(`automatic incidents, explanations and recovery render at ${width}px`,async({page,request})=>{
    await page.setViewportSize({width,height:900});
    const snapshot=await (await request.get('/api/state')).json();
    const incident={id:'test-incident',subject:'WorkshopManagement',kind:'Page unavailable',status:'Active',detected:'2026-10-10T12:00:05Z',firstObserved:'2026-10-10T12:00:00Z',context:'Test fixture: agent active',observations:[{name:'WorkshopManagement',status:200,latency:2050}],diagnosis:{cause:'API dependency may be unavailable. <script>invalid</script>',confidence:'Hypothesis / investigation required',solutions:['Inspect API logs.'],evidence:['workshopmanagementapi: exited']},ai:{status:'Completed',explanation:'Offline fallback observed.',possibleCause:'API stopped; cause unconfirmed.',solutions:['Check resource limits.'],caveat:'AI hypothesis, not confirmed',at:'2026-10-10T12:00:10Z'}};
    const monitor={enabled:true,checked:'2026-10-10T12:00:20Z',cycles:10,incidents:[incident],events:[{at:'2026-10-10T12:00:05Z',subject:'WorkshopManagement',kind:'Page unavailable',change:'Failure detected'}],baselines:[],limits:'Read-only monitoring',aiEnabled:true,samples:[{TimestampUtc:'2026-10-10T12:00:00Z',Module:'WorkshopManagement',LatencyMs:50,Healthy:true,Phase:'monitor'},{TimestampUtc:'2026-10-10T12:00:05Z',Module:'WorkshopManagement',LatencyMs:2050,Healthy:false,Phase:'monitor'}]};
    await page.route('**/api/state*',route=>route.fulfill({json:{...snapshot,monitor}}));
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/');await page.locator('[data-tab=monitor]').click();
    await expect(page.locator('#view')).toContainText('Suggested investigation and fixes');
    await expect(page.locator('#view')).toContainText('AI recommendations');
    await expect(page.locator('#view')).toContainText('Explanation ready');
    expect(await page.locator('.monitor-fixes').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(14);
    expect(await page.locator('.incident-evidence').getAttribute('open')).toBeNull();
    await page.locator('.incident-evidence summary').click();
    await expect(page.locator('.incident-evidence')).toContainText('Last incident sample: HTTP 200');
    await expect(page.locator('#view')).toContainText('Offline fallback observed');
    await expect(page.locator('#view')).toContainText('<script>invalid</script>');
    expect(await page.locator('#view script').count()).toBe(0);
    expect(await page.locator('#latency-chart').evaluate(canvas=>canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some(value=>value>0))).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
    await page.screenshot({path:`test-results/monitor-${width}.png`,fullPage:true});
    const download=page.waitForEvent('download');await page.locator('[data-monitor-download]').click();expect((await download).suggestedFilename()).toBe('monitor-incidents.json');
    incident.status='Recovered';incident.recovered='2026-10-10T12:00:30Z';incident.durationSeconds=30;
    await page.locator('#refresh').click();await expect(page.locator('#view')).toContainText('30.0 sec');
    incident.ai={status:'Queued'};
    await page.locator('#refresh').click();
    await expect(page.locator('#view')).toContainText('Waiting for AI analysis');
    await expect(page.locator('#view')).toContainText('Recovery was confirmed by healthy checks.');
    expect(errors).toEqual([]);
  });
}

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

for (const width of [1440,390]) {
  test(`3D topology is framed, moving and interactive at ${width}px`,async({page,request})=>{
    await page.setViewportSize({width,height:1000});
    const snapshot=await (await request.get('/api/state')).json();
    const health={...snapshot.health,dockerError:null,containers:(snapshot.dependencies?.services||[]).map(service=>({service,state:'running',health:'healthy'})),modules:[{name:'WorkshopManagement',healthy:true}],checked:new Date().toISOString()};
    await page.route('**/api/state*',route=>route.fulfill({json:{...snapshot,health}}));
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
    await page.goto('/');await page.locator('[data-tab=topology]').click();
    await expect(page.locator('#topology-message')).toBeHidden({timeout:20000});
    const canvas=page.locator('#topology-canvas');await expect(canvas).toBeVisible();
    await expect(page.locator('#topology-detail')).toContainText('Workshop API');
    await expect(canvas).toHaveAttribute('data-framed-nodes','13');
    const pixels=await canvas.evaluate(canvas=>{
      const gl=canvas.getContext('webgl2');const pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
      let nonblank=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>0&&(pixels[i]<200||pixels[i+1]<200||pixels[i+2]<200))nonblank++;
      return {nonblank,total:pixels.length/4};
    });expect(pixels.nonblank).toBeGreaterThan(pixels.total*.005);
    const first=await canvas.evaluate(canvas=>canvas.toDataURL());await page.waitForTimeout(1000);expect(await canvas.evaluate(canvas=>canvas.toDataURL())).not.toBe(first);
    await page.locator('[data-topology-action=rotate]').click();
    await page.locator('#topology-service').selectOption('sqlserver');await expect(page.locator('#topology-detail')).toContainText('SQL Server');
    const beforeZoom=await canvas.evaluate(canvas=>canvas.toDataURL());await page.locator('[data-topology-action=in]').click();await page.waitForTimeout(300);expect(await canvas.evaluate(canvas=>canvas.toDataURL())).not.toBe(beforeZoom);
    await page.locator('[data-topology-action=reset]').click();
    await page.screenshot({path:`test-results/topology-${width}.png`,fullPage:true});
    health.containers.find(row=>row.service==='sqlserver').state='exited';
    await page.locator('#refresh').click();await expect(page.locator('#topology-detail')).toContainText('Failure observed');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
    await page.locator('[data-tab=overview]').click();await expect(canvas).toHaveCount(0);
    await page.locator('[data-tab=topology]').click();await expect(page.locator('#topology-message')).toBeHidden();
    expect(errors).toEqual([]);
  });
}
