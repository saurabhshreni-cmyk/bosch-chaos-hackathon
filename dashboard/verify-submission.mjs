import { readFile,writeFile,stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url))),out=path.join(root,'submission');
const json=async name=>JSON.parse((await readFile(path.join(out,name),'utf8')).replace(/^\uFEFF/,''));
const manifest=await json('manifest.json'),demo=await json('demo.json');
const combinedSession=JSON.parse((await readFile(path.join(root,'docs/evidence/day2',manifest.CombinedSuite,'session.json'),'utf8')).replace(/^\uFEFF/,''));
const combined=JSON.parse((await readFile(path.join(root,'docs/evidence/day2',combinedSession.Experiments[0].RunId,'report.json'),'utf8')).replace(/^\uFEFF/,''));
const timestamp=value=>{const match=String(value).match(/^\/Date\((\d+)/);return match?Number(match[1]):Date.parse(value);};
const overlap=Math.min(timestamp(combined.Load?.FinishedUtc),timestamp(combined.RestoreCommandCompletedUtc))-Math.max(timestamp(combined.Load?.StartedUtc),timestamp(combined.FaultStartedUtc));
if(!combined.Recovered||combined.Error||!Number.isFinite(overlap)||overlap<1000||combined.Load?.Error||!combined.Load?.Results?.requests?.total)throw new Error('Combined evidence must show actual traffic overlapping the fault and verified recovery.');
for(const name of ['demo.webm','demo.vtt','architecture.pdf','dependency-map.png','findings.md','team-form.json','clean-start.json','comparison.json'])if(!(await stat(path.join(out,name))).size)throw new Error('Empty deliverable: '+name);
const pdf=(await readFile(path.join(out,'architecture.pdf'))).toString('latin1');
const pages=(pdf.match(/\/Type\s*\/Page\b/g)||[]).length;
if(pages!==1)throw new Error(`Architecture must be one page; got ${pages}.`);
if(demo.AiSession!==manifest.AiSuite||demo.CombinedSession!==manifest.CombinedSuite)throw new Error('Video provenance must match packaged execution.');
const browser=await chromium.launch({channel:'msedge',headless:true});
const media=createServer(async(req,res)=>{
  try{
    if(req.url==='/viewer'){res.setHeader('Content-Type','text/html');return res.end('<!doctype html><html><body style="margin:0"><video controls preload="auto" width="1280" height="720" src="/demo.webm"></video></body></html>');}
    if(req.url!=='/demo.webm'){res.writeHead(404);return res.end();}
    const data=await readFile(path.join(out,'demo.webm')),range=req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
    if(range){const start=Number(range[1]),end=Math.min(range[2]?Number(range[2]):data.length-1,data.length-1);if(start>end){res.writeHead(416);return res.end();}res.writeHead(206,{'Content-Type':'video/webm','Content-Range':`bytes ${start}-${end}/${data.length}`,'Accept-Ranges':'bytes','Content-Length':end-start+1});return res.end(data.subarray(start,end+1));}
    res.writeHead(200,{'Content-Type':'video/webm','Content-Length':data.length,'Accept-Ranges':'bytes'});res.end(data);
  }catch{res.writeHead(500);res.end();}
});
await new Promise(resolve=>media.listen(0,'127.0.0.1',resolve));
let duration,width,height;
try{
  const page=await browser.newPage({viewport:{width:1280,height:720}});
  page.setDefaultTimeout(20000);
  await page.goto(`http://127.0.0.1:${media.address().port}/viewer`);
  await page.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
  ({duration,width,height}=await page.locator('video').evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight})));
  if(!Number.isFinite(duration)||duration>180||duration<40||width!==1280||height!==720)throw new Error('Invalid demo video duration or dimensions.');
  const checkpoints=[demo.Captions[0].start+1,demo.Captions.find(c=>c.text.startsWith('Failure is real')).start+1,demo.Captions.find(c=>c.text.startsWith('Real model findings')).start+1];
  for(const [i,time]of checkpoints.entries()){
    await page.locator('video').evaluate((v,time)=>new Promise(resolve=>{v.pause();v.addEventListener('seeked',resolve,{once:true});v.currentTime=time;}),time);
    const variation=await page.locator('video').evaluate(v=>{
      const c=document.createElement('canvas');c.width=128;c.height=72;const ctx=c.getContext('2d');ctx.drawImage(v,0,0,128,72);const p=ctx.getImageData(0,0,128,72).data;const colors=new Set();for(let i=0;i<p.length;i+=4)colors.add(`${p[i]},${p[i+1]},${p[i+2]}`);return colors.size;
    });
    if(variation<100)throw new Error('Blank video frame.');
    const frame=await page.locator('video').evaluate(v=>{const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);return c.toDataURL('image/png').split(',')[1];});
    await writeFile(path.join(out,`demo-frame-${i+1}.png`),Buffer.from(frame,'base64'));
  }
  await page.goto(pathToFileURL(path.join(out,'architecture.html')).href);
  await page.screenshot({path:path.join(out,'architecture-preview.png'),fullPage:true});
}finally{await browser.close();await new Promise(resolve=>media.close(resolve));}
await writeFile(path.join(out,'media-verification.json'),JSON.stringify({Passed:true,VerifiedUtc:new Date().toISOString(),ArchitecturePages:pages,VideoSeconds:duration,VideoWidth:width,VideoHeight:height,NonblankFrames:3,CombinedTrafficOverlapSeconds:overlap/1000,PortalSubmitted:false},null,2));
console.log(`PASS: ${duration.toFixed(1)} second video, three nonblank frames, one-page architecture and complete deliverables.`);
