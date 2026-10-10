import autocannon from 'autocannon';
import { writeFile, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const [seconds,output]=process.argv.slice(2);
const duration=Number(seconds);
const destination=path.resolve(output||'');
const resultRoot=path.join(root,'chaos-scripts','results')+path.sep;
if(!Number.isInteger(duration)||duration<5||duration>30||!destination.startsWith(resultRoot)||path.basename(destination)!=='load.json')throw new Error('Invalid bounded local load request.');
const stopFile=path.join(root,'chaos-scripts','STOP');
const cancelFile=path.join(path.dirname(destination),'STOP-LOAD');
let completed=false;
const profile={url:'http://127.0.0.1:7005/WorkshopManagement',connections:2,pipelining:1,overallRate:10,duration,timeout:2,method:'GET',excludeErrorStats:true};
const started=new Date().toISOString();
await writeFile(path.join(path.dirname(destination),'load-ready.json'),JSON.stringify({StartedUtc:started,Profile:profile}));
const instance=autocannon(profile,async(error,result)=>{
  completed=true;clearInterval(stopPoll);
  await writeFile(destination,JSON.stringify({StartedUtc:started,FinishedUtc:new Date().toISOString(),Profile:profile,StoppedEarly:stopped,Error:error?.message||null,Results:result,Limitations:'HTTP status alone cannot distinguish the app offline fallback. Page-probe evidence is authoritative for availability.'},null,2));
  if(error)process.exitCode=1;
});
let stopped=false;
const stopPoll=setInterval(async()=>{
  if(completed)return;
  for(const file of [stopFile,cancelFile]){
    try{await access(file);stopped=true;instance.stop();return;}catch{}
  }
},200);
// Autocannon has its own deadline; this additional cap prevents orphaned traffic.
const hardStop=setTimeout(()=>{if(!completed){stopped=true;instance.stop();}},(duration+2)*1000);
hardStop.unref();
