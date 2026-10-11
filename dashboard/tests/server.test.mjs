import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { request } from 'node:http';
import { createDashboard } from '../server.mjs';
import { EvidenceStore, validateRun, validId } from '../store.mjs';

const config = { mode:'preview',engine:'rules',budget:1,baseline:3,model:'qwen2.5:1.5b',experiments:['workshop-crash'] };
test('only bounded registered tools can be requested', () => {
  assert.equal(validateRun(config),config);
  for (const change of [{budget:5},{baseline:1},{mode:'shell'},{experiments:['other-container']},{experiments:['workshop-crash','workshop-crash']},{command:'docker kill anything'},{model:'--command'},{mode:'execute'}]) assert.throws(()=>validateRun({...config,...change}));
  assert.equal(validateRun({...config,mode:'execute',confirmed:true}).confirmed,true);
  assert.equal(validateRun({...config,experiments:['workshop-crash-with-load']}).experiments[0],'workshop-crash-with-load');
  assert.equal(validateRun({...config,autoDiscover:true,experiments:['workshop-delay-high']}).autoDiscover,true);
  assert.throws(()=>validateRun({...config,autoDiscover:'true'}));
  assert.equal(validateRun({...config,mode:'detect',experiments:[]}).mode,'detect');
  assert.throws(()=>validateRun({...config,mode:'detect',experiments:['workshop-crash']}));
  assert.throws(()=>validateRun({...config,mode:'detect',experiments:[],confirmed:true}));
  assert.equal(validId('../outside'),false);
});

test('evidence resolution ignores untrusted report paths', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(),'pitstop-dashboard-test-'));
  try {
    const id='20261010T120000000Z',run='20261010T120020000Z';
    const dir=path.join(root,'agent','runs',id),results=path.join(root,'chaos-scripts','results',run);
    await mkdir(dir,{recursive:true});await mkdir(results,{recursive:true});
    const session={RunId:id,Stage:'Completed',Mode:'AI: mock',Execute:true,Plans:[],Experiments:[{RunId:run,ReportPath:'C:/private/secret.json',AnalysisPath:'../../private'}]};
    await writeFile(path.join(dir,'session.json'),'\uFEFF'+JSON.stringify(session));
    await writeFile(path.join(results,'report.json'),JSON.stringify({RunId:run,Samples:[]}));
    const store=new EvidenceStore(root),sessions=await store.sessions();
    assert.equal(sessions.length,1);
    const detail=await store.detail(sessions[0]);
    assert.equal(detail.experiments[0].report.RunId,run);
    assert.equal('ReportPath' in detail.experiments[0],false);
    assert.equal(await store.report('../private'),null);
    await writeFile(path.join(dir,'session.json'),'{"unfinished":');
    assert.deepEqual(await store.sessions(),[]);
  } finally { await rm(root,{recursive:true,force:true}); }
});

test('localhost API rejects CSRF, unsafe configuration and traversal', async () => {
  const server=createDashboard({probes:false});server.listen(0,'127.0.0.1');await once(server,'listening');
  const base=`http://127.0.0.1:${server.address().port}`;
  try {
    const state=await (await fetch(base+'/api/state')).json();
    assert.ok(state.token);
    const invalidHostStatus = await new Promise((resolve,reject)=>{
      const req=request(base+'/api/state',{headers:{Host:'attacker.example'}},response=>{response.resume();resolve(response.statusCode);});
      req.on('error',reject);req.end();
    });
    assert.equal(invalidHostStatus,403);
    assert.equal((await fetch(base+'/api/state?session=../secret')).status,400);
    assert.equal((await fetch(base+'/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)})).status,403);
    const headers={'Content-Type':'application/json','Origin':base,'X-Dashboard-Token':state.token};
    assert.equal((await fetch(base+'/api/run',{method:'POST',headers,body:JSON.stringify({...config,mode:'execute'})})).status,400);
    assert.equal((await fetch(base+'/api/run',{method:'POST',headers,body:JSON.stringify({...config,command:'arbitrary'})})).status,400);
    assert.equal((await fetch(base+'/api/download/20261010T120000000Z/../../secret')).status,404);
    assert.equal((await fetch(base+'/')).status,200);
  } finally { await new Promise(resolve=>server.close(resolve)); }
});

test('read-only mode disables all commands',async()=>{
  const server=createDashboard({probes:false,controls:false});server.listen(0,'127.0.0.1');await once(server,'listening');
  try{const response=await fetch(`http://127.0.0.1:${server.address().port}/api/stop`,{method:'POST'});assert.equal(response.status,403);}
  finally{await new Promise(resolve=>server.close(resolve));}
});

test('retained Day-2 sessions resolve only canonical evidence folders',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'pitstop-retained-test-'));
  const previous=process.env.DASHBOARD_SHOW_RETAINED;
  process.env.DASHBOARD_SHOW_RETAINED='1';
  try{
    const id='20261010T120000000Z',run='20261010T120020000Z';
    const dir=path.join(root,'docs/evidence/day2',id),results=path.join(root,'docs/evidence/day2',run);
    await mkdir(dir,{recursive:true});await mkdir(results,{recursive:true});
    await writeFile(path.join(dir,'session.json'),JSON.stringify({RunId:id,Experiments:[{RunId:run,ReportPath:'../../secret'}]}));
    await writeFile(path.join(dir,'baseline.json'),JSON.stringify({Healthy:true}));
    await writeFile(path.join(results,'report.json'),JSON.stringify({RunId:run,Recovered:true}));
    const store=new EvidenceStore(root),sessions=await store.sessions();
    assert.equal(sessions[0].RetainedDay2,true);
    assert.equal((await store.detail(sessions[0])).baseline.Healthy,true);
    assert.equal((await store.detail(sessions[0])).experiments[0].report.Recovered,true);
    assert.throws(()=>store.sessionDirectory({RunId:'../outside',RetainedDay2:true}));
  }finally{if(previous===undefined)delete process.env.DASHBOARD_SHOW_RETAINED;else process.env.DASHBOARD_SHOW_RETAINED=previous;await rm(root,{recursive:true,force:true});}
});
