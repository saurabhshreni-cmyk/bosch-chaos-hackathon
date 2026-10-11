import { readFile,writeFile,mkdir,copyFile } from 'node:fs/promises';
import { fileURLToPath,pathToFileURL } from 'node:url';
import path from 'node:path';
import { chromium } from '@playwright/test';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url))),out=path.join(root,'submission'),saved=path.join(root,'docs/evidence/day2');
const json=async file=>JSON.parse((await readFile(file,'utf8')).replace(/^\uFEFF/,''));
const [sessionId,combinedId,validationId]=process.argv.slice(2);
for(const id of [sessionId,combinedId,validationId])if(!/^\d{8}T\d{9}Z$/.test(id||''))throw new Error('Three canonical evidence IDs required.');
await mkdir(saved,{recursive:true});
const retain=async(folder,id,names)=>{const dest=path.join(saved,id);await mkdir(dest,{recursive:true});for(const name of names){try{await copyFile(path.join(folder,id,name),path.join(dest,name));}catch(e){if(e.code!=='ENOENT')throw e;}}};
const sessions=[];
for(const id of [sessionId,combinedId]){
  const s=await json(path.join(root,'agent/runs',id,'session.json'));
  if(s.Stage!=='Completed'||s.Error||!s.Experiments.every(e=>e.Recovered))throw new Error('Cannot package incomplete or unrecovered execution.');
  await retain(path.join(root,'agent/runs'),id,['session.json','baseline.json','baseline.csv','discovery.json','findings.md']);
  for(const e of s.Experiments)await retain(path.join(root,'chaos-scripts/results'),e.RunId,['report.json','samples.csv','detection.json','anomalies.json','load.json']);
  sessions.push(s);
}
const suite=sessions[0];
if(!suite.Model||suite.Experiments.length<3||new Set(suite.Experiments.map(e=>e.Category)).size<3||suite.Experiments.some(e=>!e.AiStatus.startsWith('Completed')))throw new Error('Day-2 requires three different AI-analyzed failure types.');
const validation=await json(path.join(out,'validation',validationId,'result.json'));
const workflow=await json(path.join(out,'validation',validationId,'workflow.json'));
if(!validation.Passed||!workflow.Passed)throw new Error('Clean startup and complete workflow must pass.');
await writeFile(path.join(out,'clean-start.json'),JSON.stringify({validation,workflow},null,2));
const comparison=await json(path.join(out,'comparison.json'));
for(const id of [comparison.BeforeRunId,comparison.AfterRunId])await retain(path.join(root,'chaos-scripts/results'),id,['report.json','samples.csv']);
const rows=[],findings=[],latencies=[];
const p95=values=>{const sorted=values.slice().sort((a,b)=>a-b);return sorted.length?sorted[Math.ceil(sorted.length*.95)-1]:null;};
for(const s of sessions)for(const entry of s.Experiments){
  const report=await json(path.join(saved,entry.RunId,'report.json')),analysis=await json(path.join(saved,entry.RunId,'anomalies.json'));
  const fault=report.Samples.filter(x=>x.Phase==='fault');
  rows.push(`| ${entry.ExperimentId} | ${entry.RunId} | ${fault.filter(x=>!x.Healthy).length}/${fault.length} | ${entry.RecoverySeconds} | ${entry.ProbeScore?.Value??'n/a'} | ${entry.RollbackReason} |`);
  for(const module of ['CustomerManagement','VehicleManagement','WorkshopManagement']){
    const baseline=report.Samples.filter(x=>x.Phase==='baseline'&&x.Module===module),observed=fault.filter(x=>x.Module===module);
    latencies.push(`| ${entry.ExperimentId} | ${module} | ${p95(baseline.map(x=>x.LatencyMs))} | ${p95(observed.map(x=>x.LatencyMs))??'not sampled'} | ${observed.filter(x=>!x.Healthy).length}/${observed.length} |`);
  }
  for(const f of analysis.AiFindings||[])findings.push({...f,experiment:entry.ExperimentId,run:entry.RunId});
}
findings.sort((a,b)=>({high:0,medium:1,low:2}[a.severity]??3)-({high:0,medium:1,low:2}[b.severity]??3));
let md=`# Team 28: Ranked Findings\n\nGenerated from real local execution ${suite.RunId}. Model: ${suite.Model}.\n\n## AI Experiment Ranking\n\n`;
for(const [i,r]of suite.Rankings.entries())md+=`${i+1}. **${r.id}** (${r.durationSeconds} sec): ${r.reason} Expected impact: ${r.expectedImpact}\n`;
md+='\n**Rationale review:** the small model confused crash and network-delay descriptions in some reasons above. They are retained verbatim, not corrected to look stronger. The validated ID and code-owned registry determine the actual mechanism. Natural-language correctness is not guaranteed by schema validation.\n\n## Measurements\n\n| Experiment | Evidence run | Failed fault probes / total | Verified recovery sec | Probe score /100 | Rollback |\n| --- | --- | --- | --- | --- | --- |\n'+rows.join('\n')+'\n\nFailures include HTTP-200 offline pages. Recovery is measured from completed restoration command to all-page health, not total outage time. Raw JSON and CSV retain individual latencies and timestamps.\n\n| Experiment | Module | Baseline p95 ms | Fault p95 observed ms | Failed / sampled |\n| --- | --- | --- | --- | --- |\n'+latencies.join('\n')+'\n\nEarly safety rollback can stop sampling before every module is measured. Missing fault samples are not proof of availability.\n\n## Ranked AI Interpretations\n\n';
for(const [i,f]of findings.entries())md+=`${i+1}. **[${f.severity}] ${f.title}** (${f.experiment}): ${f.explanation} Recommended fix: ${f.recommendedFix}. Evidence: ${f.run}/${f.evidenceIds.join(', ')}. Model confidence: ${f.confidence}.\n\n`;
md+='AI statements above are interpretations, not established root causes. A crash is deliberately injected; the finding is the observed propagation, fallback or recovery behavior. Read probes cannot establish data loss, writes or durable event delivery.\n\n## Applied Fix And Retest\n\nTwo-second API request budgets and single-attempt fallback replace unconditional retries, including retries of potentially non-idempotent commands. Focused tests verify healthy results, timeout fallback and one write attempt.\n\n| Module | Before p95 observed ms | After p95 observed ms | Before failures / probes | After failures / probes |\n| --- | --- | --- | --- | --- |\n';
for(const r of comparison.ModuleComparison)md+=`| ${r.Module} | ${r.BeforeP95ObservedMs} | ${r.AfterP95ObservedMs} | ${r.BeforeFailed}/${r.BeforeProbes} | ${r.AfterFailed}/${r.AfterProbes} |\n`;
md+=`\n${comparison.Limitations}\n\nWorkshop deliberately fails fast under delay. This is a responsiveness improvement with an availability tradeoff, not proof that all resilience dimensions improved. Early rollback and unequal probe counts are reported, not hidden. Matched run IDs: ${comparison.BeforeRunId} → ${comparison.AfterRunId}.\n\n## Combined Failure\n\n${sessions[1].RunId}: Workshop crash plus bounded read traffic. See its report and load.json. Autocannon's HTTP-200 counts are not healthy-page counts; page-content probes are authoritative.\n\n## Score Method\n\n${comparison.AfterScore.Method}\n\n${comparison.AfterScore.Limitations}\n\n## Validation And Residual Risks\n\nFresh Compose project with separate volumes: ${validationId}. All 13 services running; configured health checks pass; all three pages healthy; customer, vehicle, scheduling and completion workflow passed. Existing garage data was not cleared. Cached rebuilt images were used, not an uncached rebuild.\n\nLegacy application transitive NuGet dependencies emit high-severity vulnerability warnings. Sandbox demonstration only, not production readiness. Remaining work: durability/write-fault tests, repeated controlled trials, targeted legacy dependency upgrades and model-evaluation coverage. Dashboard npm audit is clean after a scoped UUID override.\n`;
await writeFile(path.join(out,'findings.md'),md);
const team={Team:'Team No. 28',Members:['Saurabh Dwadesh Shreni','Arpit Pal','Tigisha P. Pradhan','Vansh Makhija','Omkar Singh'],Repository:'https://github.com/saurabhshreni-cmyk/bosch-chaos-hackathon',Application:'Pitstop (Apache-2.0)',Tools:['Docker Desktop / Docker Compose','PowerShell','Node.js','Ollama','Microsoft Edge'],Models:[suite.Model],Libraries:['Polly / existing .NET libraries','autocannon 8 (MIT)','lucide 1.55 (ISC)','Playwright 1.64 (Apache-2.0)'],Data:'Synthetic local garage workflow plus local read-probe measurements; no external dataset.',SubmissionPortal:null,SubmissionDeadline:'2026-10-11; exact time not supplied',Submitted:false};
team.Libraries.push('Three.js 0.186.1 (MIT)');
await writeFile(path.join(out,'team-form.json'),JSON.stringify(team,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto('http://127.0.0.1:7010');await page.waitForFunction(()=>document.querySelector('#session-label')?.textContent.startsWith('Session '));await page.locator('[data-tab="dependencies"]').click();await page.locator('#dependency-graph').waitFor();await page.waitForTimeout(1000);
  await page.locator('#dependency-graph').screenshot({path:path.join(out,'dependency-map.png')});
  await page.goto(pathToFileURL(path.join(out,'architecture.html')).href);await page.pdf({path:path.join(out,'architecture.pdf'),format:'A4',printBackground:true});
}finally{await browser.close();}
await writeFile(path.join(out,'manifest.json'),JSON.stringify({GeneratedUtc:new Date().toISOString(),AiSuite:sessionId,CombinedSuite:combinedId,CleanValidation:validationId,Deliverables:['../README.md','demo.webm','architecture.pdf','findings.md','team-form.json'],PortalSubmitted:false},null,2));
console.log('Evidence retained; findings, architecture PDF, team form and manifest generated.');
