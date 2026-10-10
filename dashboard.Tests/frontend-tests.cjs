const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function run() {
  const root = path.join(__dirname, '..', 'dashboard', 'wwwroot');
  const elements = new Map();
  const buttons = [{disabled: false, addEventListener() {}}];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: '', textContent: '', value: '', disabled: false, hidden: true,
      style: {}, classList: {add() {}, toggle() {}}, addEventListener() {},
      querySelectorAll(selector) { return selector === '[data-run]' ? buttons : []; }
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: {getElementById: element},
    window: {confirm: () => false},
    setTimeout() {}, console,
    fetch: async () => { throw new Error('No real network in frontend tests'); }
  });
  for (const name of ['presentation.js', 'app.js', 'ai.js']) {
    let source = fs.readFileSync(path.join(root, name), 'utf8');
    if (name === 'app.js') source = source.replace(/\nrefresh\(\);\s*$/, '');
    if (name === 'ai.js') source = source.replace(/\nrefreshAiStatus\(\);\s*$/, '');
    vm.runInContext(source, context, {filename: name});
  }
  const evaluate = source => vm.runInContext(source, context);
  assert.equal(evaluate("dashboardPresentation.escape('<img onerror=\"attack\">')"),
               '&lt;img onerror=&quot;attack&quot;&gt;');
  assert.equal(evaluate("dashboardPresentation.summary({services:[{running:true,health:'unknown'}]}).healthy"), 0);
  assert.equal(evaluate("dashboardPresentation.summary({services:[{running:true,health:'unknown'}]}).unmeasured"), 1);

  evaluate("state={experiments:[{name:'kill-service',risk:'medium',target:'api',minDuration:5,maxDuration:60,defaultDuration:25}],run:{isRunning:false},killSwitchEngaged:false}; backendReachable=true; renderExperiments();");
  const initial = element('experiments').innerHTML;
  element('dur-kill-service').value = '42';
  element('blockers-kill-service').innerHTML = 'Preflight passed';
  evaluate("renderExperiments();");
  assert.equal(element('dur-kill-service').value, '42');
  assert.equal(element('blockers-kill-service').innerHTML, 'Preflight passed');
  assert.equal(element('experiments').innerHTML, initial);
  evaluate("state.killSwitchEngaged=true; renderExperiments();");
  assert.equal(buttons[0].disabled, true);
  evaluate("state.killSwitchEngaged=false; backendReachable=false; renderExperiments();");
  assert.equal(buttons[0].disabled, true);
  evaluate("backendReachable=true; state.run.isRunning=true; renderExperiments();");
  assert.equal(buttons[0].disabled, true);
  evaluate("renderExplanation({summary:'<script>alert(1)</script>',evidenceCited:['raw.path']},'run','groq',[{label:'Graceful degradation / Earned',value:'0',reference:'raw.path',resolved:true}]);");
  const explanation = element('ai-explanation').innerHTML;
  assert.ok(explanation.includes('Graceful degradation / Earned'));
  assert.ok(explanation.includes('Verified field:'));
  assert.ok(explanation.includes('&lt;script&gt;'));
  assert.ok(!explanation.includes('<script>'));
  evaluate("currentTarget=null; state.graph={nodes:[{name:'webapp',kind:'frontend'},{name:'rabbitmq',kind:'infrastructure'}],edges:[{from:'webapp',to:'rabbitmq',kind:'rest'}]}; state.services=[{name:'rabbitmq',running:true,health:'unknown'}]; renderGraph();");
  assert.ok(element('graph').innerHTML.includes('marker-end="url(#dependency-arrow)"'));
  assert.ok(element('graph').innerHTML.includes('node infra unmeasured'));
  evaluate("state.services[0].health='unhealthy'; renderGraph();");
  assert.ok(element('graph').innerHTML.includes('node infra unavailable'));

  evaluate("state.run.isRunning=false; state.killSwitchEngaged=false; backendReachable=true; state.experiments=[{name:'network-delay',target:'api',risk:'medium',minDuration:5,maxDuration:60,defaultDuration:20,supportsDelay:true,minDelayMs:50,maxDelayMs:2000,defaultDelayMs:400}]; renderExperiments();");
  element('delay-network-delay').value='650';
  evaluate("state.experiments[0].recoveryPlan='Updated recovery'; renderExperiments();");
  assert.equal(element('delay-network-delay').value,'650');
  assert.ok(evaluate("dashboardPresentation.validateExperiment(state.experiments[0],20,NaN)").includes('Delay'));
  assert.ok(evaluate("dashboardPresentation.validateExperiment(state.experiments[0],20,0)").includes('Delay'));
  assert.ok(evaluate("dashboardPresentation.validateExperiment(state.experiments[0],20,2001)").includes('Delay'));
  assert.ok(evaluate("dashboardPresentation.validateExperiment(state.experiments[0],20,50.5)").includes('Delay'));
  assert.equal(evaluate("dashboardPresentation.validateExperiment(state.experiments[0],20,650)"),null);
  assert.ok(evaluate("dashboardPresentation.validateExperiment(state.experiments[0],4,650)").includes('Duration'));

  evaluate("state.preparedExperiments=[{name:'pause-customer-api',target:'api',fault:'<script>bad</script>',recovery:'unpause',status:'Awaiting live cleanup verification',scriptAvailable:true,defaultDuration:15,maxDuration:60}]; renderPreparedExperiments();");
  assert.equal(element('prepared-panel').hidden,false);
  assert.ok(element('prepared-experiments').innerHTML.includes('&lt;script&gt;'));
  assert.ok(!element('prepared-experiments').innerHTML.includes('<button'));
  assert.ok(element('prepared-experiments').innerHTML.includes('pending verification'));
  evaluate("state.preparedExperiments=[]; renderPreparedExperiments();");
  assert.equal(element('prepared-panel').hidden,true);

  evaluate("renderDiscoveries({discoveries:[{title:'<img onerror=attack>',status:'not executable',failureMode:'<script>bad</script>',evidence:['<svg>']}],discoveriesRejected:['<script>rejected</script>']});");
  assert.ok(!element('ai-discoveries').innerHTML.includes('<script>'));
  assert.ok(element('ai-discoveries').innerHTML.includes('&lt;img'));
  evaluate("state.killSwitchEngaged=true; aiRecommendation={allowed:true,resolved:{experiment:'network-delay'},recommendation:{durationSeconds:20},preflight:{ok:true}}; renderRecommendation(aiRecommendation);");
  assert.ok(element('ai-recommendation').innerHTML.includes('id="btn-ai-approve" disabled'));

  let requests=0;
  context.fetch=async()=>{requests++;throw new Error('No network expected');};
  element('dur-network-delay').value='20';
  element('delay-network-delay').value='650';
  await evaluate("approveAndRun('network-delay')");
  assert.equal(requests,0);
  evaluate("state.killSwitchEngaged=false;");
  element('delay-network-delay').value='';
  await evaluate("approveAndRun('network-delay')");
  assert.equal(requests,0);
  evaluate("aiRecommendation={allowed:false,resolved:{experiment:'network-delay'},preflight:{ok:true}};");
  await evaluate("runRecommended()");
  assert.equal(requests,0);

  context.fetch=async()=>({ok:true,status:200,json:async()=>({mode:'Groq',modes:['Groq'],activeProvider:'groq',providers:[{provider:'groq',model:'test',available:true},{provider:'ollama',model:'disabled',available:false}]})});
  await evaluate("refreshAiStatus()");
  assert.equal(element('ai-mode').disabled,true);
  assert.ok(!element('provider-status').innerHTML.includes('ollama'));
  return '36 frontend regression checks passed; all three scripts parsed successfully';
}
module.exports = run;
if (require.main === module) run().then(console.log).catch(err => { console.error(err); process.exitCode = 1; });
