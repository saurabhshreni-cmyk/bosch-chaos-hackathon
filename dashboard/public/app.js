const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const list = value => value == null ? [] : Array.isArray(value) ? value : [value];
const icons = () => window.lucide?.createIcons();
const labels = { 'workshop-crash': 'Workshop crash', 'database-crash': 'Database crash', 'rabbitmq-crash': 'RabbitMQ crash', 'workshop-delay': 'Network delay', 'workshop-crash-with-load': 'Workshop crash + traffic' };
const moduleLabels = { CustomerManagement: 'Customer', VehicleManagement: 'Vehicle', WorkshopManagement: 'Workshop' };
const colors = { CustomerManagement: '#007f79', VehicleManagement: '#3976b6', WorkshopManagement: '#cf2858' };
let state, selectedId = null, tab = 'overview', chartScope = null, pending = false, polling = false;
let formConfig = null;
function date(value) {
  if (!value) return null;
  const legacy = String(value).match(/^\/Date\((\d+)/);
  return legacy ? new Date(Number(legacy[1])) : new Date(value);
}
function idDate(id) { return id ? date(`${id.slice(0,4)}-${id.slice(4,6)}-${id.slice(6,8)}T${id.slice(9,11)}:${id.slice(11,13)}:${id.slice(13,15)}.${id.slice(15,18)}Z`) : null; }
function time(value) { const parsed = date(value); return parsed && !isNaN(parsed) ? parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : '--'; }
function badge(text, kind = '') { return `<span class="badge ${kind}">${escape(text)}</span>`; }
function icon(name) { return `<i data-lucide="${name}"></i>`; }
function section(title, content, meta = '') { return `<section class="section"><div class="section-heading"><h2>${escape(title)}</h2><span>${escape(meta)}</span></div>${content}</section>`; }
function empty(text) { return `<div class="empty">${escape(text)}</div>`; }
function terminal(stage = '') { return stage === 'Completed' || stage.startsWith('Plans only') || stage === 'Stopped with error'; }
function active() { return !!(state?.job?.running || state?.locks?.Agent || state?.locks?.Experiment); }
function setMessage(message, error = false) { $('#action-message').textContent = message; $('#action-message').classList.toggle('error', error); }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; setTimeout(() => { $('#toast').hidden = true; }, 5000); }

async function refresh() {
  if (polling) return;
  polling = true;
  try {
    const response = await fetch(`/api/state${selectedId ? `?session=${encodeURIComponent(selectedId)}` : ''}`, { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error('Dashboard connection unavailable');
    const next = await response.json();
    // A snapshot may briefly be between file writes; retain the last selected evidence.
    if (!next.selected && state?.selected?.RunId === selectedId) next.selected = state.selected;
    if (next.selected && state?.selected && next.selected.RunId === state.selected.RunId) {
      for (const key of ['baseline', 'liveBaseline', 'liveExperiment']) {
        if (!next.selected[key]) next.selected[key] = state.selected[key];
      }
    }
    state = next;
    $('#connection').hidden = true;
    if (!selectedId && state.selected) selectedId = state.selected.RunId;
    render();
  } catch {
    $('#connection').hidden = false;
    $('#connection').textContent = 'Connection lost. Displayed evidence is the last received snapshot; controls are unavailable.';
    $('#preview').disabled = $('#execute').disabled = $('#stop').disabled = true;
  } finally { polling = false; }
}

function render() {
  const session = state.selected;
  $('#session-count').textContent = state.sessions.length;
  const entries = state.sessions.map(item => {
    const label = idDate(item.id)?.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) || item.id;
    const bad = item.stage === 'Stopped with error';
    return `<button class="session-item ${item.id === selectedId ? 'active' : ''}" data-session="${escape(item.id)}"><strong>${escape(label)}</strong><small>${item.execute ? 'Execution' : 'Plan preview'} / ${item.mode.startsWith('AI') ? 'Local AI' : 'Fixed order'}</small><span class="tiny-status"><span class="dot ${bad ? 'bad' : terminal(item.stage) ? '' : 'unknown'}"></span>${escape(item.stage === 'Completed' ? `${item.count} experiments completed` : item.stage.startsWith('Plans only') ? 'Plan only' : item.stage)}</span></button>`;
  }).join('');
  $('#session-list').innerHTML = entries || empty('No sessions recorded');
  $('#mobile-session').innerHTML = state.sessions.map(item => `<option value="${escape(item.id)}" ${item.id === selectedId ? 'selected' : ''}>${escape(idDate(item.id)?.toLocaleString())} / ${item.execute ? 'Execute' : 'Preview'}</option>`).join('') || '<option>No recorded sessions</option>';
  $('#session-label').textContent = session ? `Session ${session.RunId}${session.Retained ? ' / retained evidence' : ''}` : state.job?.running ? `Session ${state.job.id} / starting` : 'No session selected';
  const stage = currentStage(session);
  $('#status-line').innerHTML = badge(stage, session?.Error || stage?.startsWith('Incomplete') ? 'bad' : active() && !terminal(session?.Stage) ? 'teal' : 'good') + badge(session?.Mode || 'No planner run', session?.Model ? 'teal' : '') + badge(session?.Execute ? 'Fault execution' : 'Plan only') + `<span class="muted">${session?.UpdatedUtc ? `Updated ${escape(time(session.UpdatedUtc))}` : 'Historical evidence'}</span>`;
  $('#stop-banner').hidden = !state.stop;
  $('#reset-stop').disabled = active() || pending || !state.controls;
  $('#switch-status').textContent = state.stop ? 'STOP requested' : 'Armed';
  $('#stop').disabled = !state.controls || pending;
  $('#preview').disabled = $('#execute').disabled = !state.controls || active() || pending || state.stop;
  $('#download').disabled = !session;
  if (state.locks.error) setMessage(state.locks.error, true);
  else if (!state.controls) setMessage('Read-only dashboard.');
  else if (active() && state.job?.id !== selectedId) setMessage('A sandbox session is active.');
  const names = state.health.model.models;
  if (names.length && JSON.stringify(names) !== $('#model').dataset.names) {
    const existing = $('#model').value;
    $('#model').innerHTML = names.map(name => `<option>${escape(name)}</option>`).join('');
    if (names.includes(existing)) $('#model').value = existing;
    $('#model').dataset.names = JSON.stringify(names);
  }
  $('#model-status').textContent = !state.health.checked ? 'Checking model server...' : state.health.model.available ? `${names.length} installed model${names.length === 1 ? '' : 's'} / localhost:11434` : 'Ollama unavailable';
  $('#model').disabled = $('input[name=engine]:checked').value === 'rules';
  $('#infrastructure').innerHTML = ['sqlserver', 'rabbitmq', 'webapp'].map(name => {
    const item = state.health.containers.find(row => row.service === name);
    const good = item?.state === 'running' && item.health !== 'unhealthy';
    return `<div class="infra-row"><span><span class="dot ${!item ? 'unknown' : good ? '' : 'bad'}"></span>${escape(name === 'sqlserver' ? 'SQL Server' : name === 'rabbitmq' ? 'RabbitMQ' : 'Web app')}</span><small>${escape(item ? item.health || item.state : 'Unknown')}</small></div>`;
  }).join('') + `<div class="infra-row"><span>${icon('cpu')} Local model</span><small>${state.health.model.available ? 'Available' : 'Offline'}</small></div>`;
  renderMetrics(session);
  renderView(session);
  icons();
}

function currentStage(session) {
  if (state.job?.id === selectedId && !state.job.running && state.job.exitCode !== 0) return 'Stopped with error';
  if (!session) return state.job?.running ? state.job.stage : 'Ready';
  const updated = date(session.UpdatedUtc) || idDate(session.RunId);
  if (!terminal(session.Stage) && !active() && state.locks.checked && !state.locks.error && updated && Date.now()-updated.getTime()>30000) return 'Incomplete session / agent inactive';
  if (session.Stage?.startsWith('Executing') && session.liveExperiment && (!session.UpdatedUtc || date(session.liveExperiment.UpdatedUtc)>=date(session.UpdatedUtc))) return session.liveExperiment.Stage;
  return session.Stage;
}

function experimentSamples(session) {
  const result = list(session?.experiments).flatMap(item => list(item.report?.Samples));
  if (session?.liveExperiment && !list(session.experiments).some(item => item.RunId === session.liveExperiment.RunId)) result.push(...list(session.liveExperiment.Samples));
  return result;
}

function renderMetrics(session) {
  const experiments = list(session?.experiments), faults = experimentSamples(session).filter(row => row.Phase === 'fault');
  const failed = faults.filter(row => !row.Healthy).length;
  const anomalies = experiments.reduce((sum, row) => sum + (row.AnomalyCount || 0), 0);
  const verified = experiments.filter(row => row.Recovered).length;
  const metrics = [
    ['Experiments', experiments.length, `${list(session?.Plans).length} plans selected`],
    ['Fault error rate', faults.length ? `${Math.round(failed / faults.length * 100)}%` : '--', `${failed} / ${faults.length} fault-phase probes`],
    ['Anomalous samples', experiments.length ? anomalies : '--', 'Completed experiment analysis'],
    ['Recovery verified', experiments.length ? `${verified}/${experiments.length}` : '--', 'All three module pages'],
  ];
  $('#metrics').innerHTML = metrics.map((row, index) => `<div class="metric"><div class="label">${escape(row[0])}</div><strong class="${index === 3 ? 'accent' : ''}">${escape(row[1])}</strong><small>${escape(row[2])}</small></div>`).join('');
}

function pipeline(session) {
  const stage = currentStage(session) || '';
  let current = 0;
  if (/Planning|Ranking|Ranked plan|Plan validated|Plans only/.test(stage)) current = 1;
  if (/Injecting|Fault|Preflight|Executing/.test(stage)) current = 2;
  if (/Restor|Verifying|Recovered/.test(stage)) current = 3;
  if (/Analyz|analysis recorded|Completed/.test(stage)) current = 4;
  const finished = session?.Stage === 'Completed';
  const names = [['Baseline','gauge','Healthy gate'], ['Plan','brain-circuit','Allowlist validated'], ['Inject','zap','Bounded fault'], ['Recover','rotate-ccw','Restoration verified'], ['Analyze','file-chart-column','Evidence referenced']];
  let content = `<div class="pipeline">${names.map((item,index) => `<div class="pipeline-step ${index === current ? 'current' : index < current || finished ? 'done' : ''}"><span class="step-icon">${icon(item[1])}</span><strong>${item[0]}</strong><small>${item[2]}</small></div>`).join('')}</div>`;
  const live = session?.liveBaseline;
  if (session?.Stage === 'Collecting baseline' && live) {
    const percent = Math.min(100, live.ElapsedSeconds / live.DurationSeconds * 100);
    content += `<div class="progress"><span data-progress="${percent}"></span></div><div class="progress-label"><span>${list(live.Samples).length} recorded probes</span><span>${Math.round(live.ElapsedSeconds)} / ${live.DurationSeconds} sec</span></div>`;
  }
  if (session?.Error) content += `<div class="error-block">${escape(session.Error)}</div>`;
  return section('Agent lifecycle', content, stage);
}

function healthSection() {
  const content = ['CustomerManagement', 'VehicleManagement', 'WorkshopManagement'].map(name => {
    const row = state.health.modules.find(item => item.name === name);
    return `<div class="health-item ${row && !row.healthy ? 'failed' : ''}"><strong><span class="dot ${!row ? 'unknown' : row.healthy ? '' : 'bad'}"></span>${moduleLabels[name]}</strong><span class="health-value">${row ? `${row.latency}<small> ms</small>` : '--'}</span><small>${row ? row.healthy ? 'Page responding' : row.timeout ? 'Timeout / connection failure' : 'Offline fallback / failed status' : 'Awaiting probe'}</small></div>`;
  }).join('');
  return section('Live module probes', `<div class="health-grid">${content}</div>`, state.health.checked ? `${time(state.health.checked)} / 2 sec timeout` : 'Current sandbox');
}

function chartData(session) {
  if (!session) return [];
  if (chartScope === 'baseline') return list(session.baseline?.Samples || session.liveBaseline?.Samples);
  if (chartScope === 'live' || !chartScope && session.liveExperiment) return list(session.liveExperiment.Samples);
  const report = list(session.experiments).find(item => item.RunId === chartScope) || list(session.experiments).at(-1);
  return list(report?.report?.Samples || session.baseline?.Samples || session.liveBaseline?.Samples);
}

function chartSection(session) {
  const experiments = list(session?.experiments);
  const selected = chartScope || (session?.liveExperiment ? 'live' : experiments.at(-1)?.RunId || 'baseline');
  const options = [{ id: 'baseline', label: 'Session baseline' }];
  if (session?.liveExperiment) options.push({ id: 'live', label: `Latest experiment / ${session.liveExperiment.Stage}` });
  for (const item of experiments) options.push({ id: item.RunId, label: labels[item.ExperimentId] || item.ExperimentId });
  return `<section class="section"><div class="section-heading"><h2>Request latency</h2><select id="chart-scope" class="chart-select" aria-label="Latency evidence">${options.map(option => `<option value="${escape(option.id)}" ${option.id === selected ? 'selected' : ''}>${escape(option.label)}</option>`).join('')}</select></div><div class="legend"><span><i class="customer"></i>Customer</span><span><i class="vehicle"></i>Vehicle</span><span><i class="workshop"></i>Workshop</span><span>Timeouts are lower bounds</span></div><div class="chart-wrap"><canvas id="latency-chart" role="img" aria-label="Recorded request latency by module over time"></canvas></div></section>`;
}

function plansSection(session) {
  const content = list(session?.Plans).map((plan, index) => `<article class="plan"><span class="plan-number">${index + 1}</span><div><div class="plan-title"><strong>${escape(labels[plan.id] || plan.id)}</strong>${badge(`${plan.durationSeconds} sec`)}${badge('Validated', 'teal')}</div><p>${escape(plan.reason)}</p><div class="hypothesis"><strong>Predicted impact:</strong> ${escape(plan.expectedImpact)}</div></div></article>`).join('');
  const ranking = list(session?.Rankings).map((plan,index)=>`<li><strong>${index+1}. ${escape(labels[plan.id]||plan.id)}</strong><span>${escape(plan.reason)}</span></li>`).join('');
  return (ranking ? section('AI experiment ranking',`<ol class="timeline">${ranking}</ol>`,'Ranked from dependency map and baseline') : '') + section('Selected plans', `<div class="plan-list">${content || empty('No plans selected yet')}</div>`, session?.Model ? 'AI hypothesis / not an observed result' : 'Fixed catalog order');
}

function resultsSection(session) {
  const rows = list(session?.experiments).map(item => `<tr><td><strong>${escape(labels[item.ExperimentId] || item.ExperimentId)}</strong><br><span class="muted">${escape(item.Category)}${item.ProbeScore?.Value!=null ? ` / probe score ${escape(item.ProbeScore.Value)}/100` : ''}</span></td><td>${badge(item.Recovered ? 'Verified' : 'Unverified', item.Recovered ? 'good' : 'bad')}</td><td>${item.RecoverySeconds == null ? '--' : `${escape(item.RecoverySeconds)} s`}</td><td>${escape(item.AnomalyCount ?? '--')}</td><td>${escape(item.RollbackReason)}</td></tr>`).join('');
  return section('Experiment results', rows ? `<div class="table-wrap"><table><thead><tr><th>Experiment</th><th>Recovery</th><th>After restore</th><th>Anomalies</th><th>Rollback reason</th></tr></thead><tbody>${rows}</tbody></table></div>` : empty('No completed experiments'), 'Recorded evidence');
}

function activitySection(session) {
  const events = list(session?.Events);
  const timeline = events.length ? `<ol class="timeline">${events.map(item => `<li><time>${escape(time(item.TimestampUtc))}</time><span>${escape(item.Stage)}</span></li>`).reverse().join('')}</ol>` : empty('No timestamped lifecycle history in this session');
  const job = state.job?.id === selectedId ? state.job : null;
  const logs = job?.log?.length ? `<details><summary>Agent output (${job.log.length} lines)</summary><pre class="log-view">${escape(job.log.map(line => `${time(line.at)}  ${line.text}`).join('\n'))}</pre></details>` : '';
  return section('Activity', timeline + logs, job?.running ? 'Running from dashboard' : 'Session events');
}

function findingsSection(session) {
  const all = list(session?.experiments).flatMap(item => list(item.analysis?.AiFindings).map(finding => ({ ...finding, experiment: item.ExperimentId, run: item.RunId })));
  const order = { high: 0, medium: 1, low: 2 };
  all.sort((a,b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
  const content = all.map(item => `<article class="finding ${escape(item.severity)}">${badge(item.severity, item.severity === 'high' ? 'bad' : 'warn')} <span class="review-label">AI interpretation / review required</span><h3>${escape(item.title)}</h3><p>${escape(item.explanation)}</p><p class="fix"><strong>Recommended fix:</strong> ${escape(item.recommendedFix)}</p><div class="refs">${escape(labels[item.experiment])} / confidence ${escape(item.confidence)} / evidence ${escape(item.run)}: ${escape(list(item.evidenceIds).join(', '))}</div></article>`).join('');
  return section('Ranked AI findings', content || empty(session?.Model ? 'No AI findings available yet' : 'No AI used in this session'), all.length ? `${all.length} evidence-linked findings` : 'Pending or not configured');
}

function evidenceSection(session) {
  const anomalies = list(session?.experiments).flatMap(item => list(item.analysis?.Anomalies).map(row => ({ ...row, run: item.RunId })));
  const rows = anomalies.map(row => `<tr><td>${escape(row.run)}<br><strong>${escape(row.EvidenceId)}</strong></td><td>${escape(moduleLabels[row.Module])}<br>${escape(row.Phase)}</td><td>${badge(row.Kind, row.Severity === 'high' ? 'bad' : 'warn')}</td><td>${escape(row.LatencyMs)} ms</td><td>${escape(row.BaselineMedianMs)} ms</td><td>${escape(row.ThresholdMs)} ms</td></tr>`).join('');
  const stats = list(session?.baseline?.ModuleStats);
  const baselineRows = stats.map(row => `<tr><td>${escape(moduleLabels[row.Module])}</td><td>${row.Samples}</td><td>${row.Failures}</td><td>${(row.ErrorRate*100).toFixed(1)}%</td><td>${Number(row.MedianMs).toFixed(1)} ms</td><td>${Number(row.P95Ms).toFixed(1)} ms</td></tr>`).join('');
  return section('Baseline evidence', baselineRows ? `<div class="table-wrap"><table><thead><tr><th>Module</th><th>Samples</th><th>Failures</th><th>Error rate</th><th>Median</th><th>p95</th></tr></thead><tbody>${baselineRows}</tbody></table></div>${session.baseline.Healthy ? badge('Healthy baseline', 'good') : badge('Unhealthy baseline', 'bad')}` : empty('Baseline is not complete')) + findingsSection(session) + section('Measured anomalies', rows ? `<div class="table-wrap"><table><thead><tr><th>Evidence</th><th>Module / phase</th><th>Observation</th><th>Latency</th><th>Baseline</th><th>Threshold</th></tr></thead><tbody>${rows}</tbody></table></div>` : empty('No analyzed anomalous samples')) + section('Report export', `<div class="evidence-note">Read probes do not establish write correctness, message durability, or background-worker recovery. AI recommendations are hypotheses. No calibrated resilience score is claimed.</div><button id="download-findings" ${session ? '' : 'disabled'}>${icon('file-down')} Download findings</button>`);
}

function dependenciesSection() {
  const map = state.dependencies;
  const content = `<div class="graph-wrap"><canvas id="dependency-graph" role="img" aria-label="Pitstop HTTP, SQL, event and email dependencies"></canvas></div><div class="graph-key"><span>Teal / HTTP</span><span>Gray / SQL</span><span>Blue / events</span><span>Pink / SMTP</span></div><div class="edge-list">${list(map?.edges).map(edge => `<div><strong>${escape(edge.from)}</strong> &rarr; ${escape(edge.to)}<small>${escape(edge.type)}</small></div>`).join('')}</div>`;
  return section('Mapped dependencies', content, 'Compose and source map / current sandbox health') + section('Map provenance', `<div class="evidence-note">${escape(map?.source)}<br>${escape(map?.limitations)}</div>`);
}

function renderView(session) {
  const logOpen = $('#view details')?.open;
  $('#view').innerHTML = tab === 'dependencies' ? dependenciesSection() : tab === 'evidence' ? evidenceSection(session) : pipeline(session) + healthSection() + chartSection(session) + resultsSection(session) + plansSection(session) + activitySection(session);
  if (logOpen && $('#view details')) $('#view details').open = true;
  const progress = $('#view [data-progress]');
  if (progress) progress.style.width = `${progress.dataset.progress}%`;
  if (tab === 'overview') drawChart(chartData(session));
  if (tab === 'dependencies') drawGraph();
}

function canvasContext(selector) {
  const canvas = $(selector);
  if (!canvas) return null;
  const { width, height } = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const context = canvas.getContext('2d'); context.scale(ratio,ratio);
  return { context, width, height };
}

function drawChart(samples) {
  const surface = canvasContext('#latency-chart'); if (!surface) return;
  const { context: ctx, width, height } = surface;
  ctx.fillStyle = '#fff'; ctx.fillRect(0,0,width,height); ctx.font = '10px Segoe UI';
  if (!samples.length) { ctx.fillStyle = '#63727b'; ctx.textAlign = 'center'; ctx.fillText('No measured samples yet', width/2,height/2); return; }
  const rows = samples.filter(row => Number.isFinite(Number(row.LatencyMs))).sort((a,b) => Date.parse(a.TimestampUtc)-Date.parse(b.TimestampUtc));
  const left = 45, top = 20, bottom = height-27, right = width-10;
  const max = Math.max(100, ...rows.map(row => Number(row.LatencyMs))) * 1.12;
  const start = Date.parse(rows[0].TimestampUtc), end = Math.max(start+1000, Date.parse(rows.at(-1).TimestampUtc));
  const x = row => left + (Date.parse(row.TimestampUtc)-start)/(end-start)*(right-left);
  const y = value => bottom - value/max*(bottom-top);
  let phase = null, phaseStart = null;
  const phases = [];
  for (const row of rows) { if (row.Phase !== phase) { if (phase) phases.push([phase,phaseStart,x(row)]); phase = row.Phase; phaseStart = x(row); } }
  phases.push([phase,phaseStart,right]);
  for (const [label, from, to] of phases) {
    ctx.fillStyle = label === 'fault' ? '#fff0f3' : label === 'recovery' ? '#ecf7f2' : '#f7f9fa'; ctx.fillRect(from,top,to-from,bottom-top);
    if (to-from > 50) { ctx.fillStyle = '#82939b'; ctx.fillText(label,from+5,top+12); }
  }
  for (let tick=0;tick<=4;tick++) {
    const value = max/4*tick, pos = y(value); ctx.strokeStyle = '#e3e9ec'; ctx.beginPath(); ctx.moveTo(left,pos); ctx.lineTo(right,pos); ctx.stroke();
    ctx.fillStyle = '#7b8b94'; ctx.textAlign = 'right'; ctx.fillText(value >= 1000 ? `${(value/1000).toFixed(1)}s` : `${Math.round(value)}ms`,left-7,pos+3);
    ctx.textAlign = 'center'; const timestamp = start+(end-start)*tick/4;
    ctx.fillText(time(new Date(timestamp).toISOString()).slice(3),left+(right-left)*tick/4,height-8);
  }
  for (const name of Object.keys(colors)) {
    const points = rows.filter(row => row.Module === name);
    ctx.strokeStyle = colors[name]; ctx.lineWidth = 1.8; ctx.beginPath();
    points.forEach((row,index) => index ? ctx.lineTo(x(row),y(row.LatencyMs)) : ctx.moveTo(x(row),y(row.LatencyMs))); ctx.stroke();
    for (const row of points) { ctx.fillStyle = colors[name]; ctx.beginPath(); ctx.arc(x(row),y(row.LatencyMs),row.Healthy ? 2 : 3.5,0,Math.PI*2); ctx.fill(); }
  }
}

function drawGraph() {
  const surface = canvasContext('#dependency-graph'); if (!surface) return;
  const { context: ctx, width: w, height: h } = surface;
  const nodes = {
    webapp:[.5,.08,'Web app'], customermanagementapi:[.17,.28,'Customer API'], vehiclemanagementapi:[.5,.28,'Vehicle API'], workshopmanagementapi:[.83,.28,'Workshop API'],
    sqlserver:[.27,.51,'SQL Server'], rabbitmq:[.73,.51,'RabbitMQ'],
    workshopmanagementeventhandler:[.13,.73,'Workshop','event handler'], notificationservice:[.38,.73,'Notification'], invoiceservice:[.63,.73,'Invoice'], auditlogservice:[.88,.73,'Audit log'],
    mailserver:[.23,.93,'MailDev'], timeservice:[.77,.93,'Time service'], logserver:[.5,.93,'Seq logs'],
  };
  const box = Math.min(105, w/4-10), boxH = 38;
  ctx.clearRect(0,0,w,h);
  for (const edge of list(state.dependencies?.edges)) {
    const a = nodes[edge.from], b = nodes[edge.to]; if (!a || !b) continue;
    const color = edge.type === 'HTTP' ? '#41a59b' : edge.type === 'SQL' ? '#acbbc3' : edge.type === 'SMTP' ? '#d697a9' : '#83acd2';
    const ax=a[0]*w,ay=a[1]*h+(b[1]>a[1]?boxH/2:-boxH/2), bx=b[0]*w,by=b[1]*h+(b[1]>a[1]?-boxH/2:boxH/2);
    ctx.strokeStyle=color; ctx.lineWidth=1.1; ctx.beginPath(); ctx.moveTo(ax,ay); ctx.bezierCurveTo(ax,(ay+by)/2,bx,(ay+by)/2,bx,by); ctx.stroke();
    const direction=by>ay?1:-1;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(bx,by);ctx.lineTo(bx-3,by-5*direction);ctx.lineTo(bx+3,by-5*direction);ctx.fill();
  }
  for (const [name, [xx,yy,label,second]] of Object.entries(nodes)) {
    const x=xx*w,y=yy*h;
    const moduleName = { customermanagementapi:'CustomerManagement',vehiclemanagementapi:'VehicleManagement',workshopmanagementapi:'WorkshopManagement' }[name];
    const row=state.health.modules.find(item=>item.name===moduleName);
    ctx.fillStyle=name==='webapp'?'#182126':'#fff';ctx.strokeStyle=row && !row.healthy?'#cf2858':'#bccbd2';ctx.lineWidth=1;ctx.beginPath();ctx.roundRect(x-box/2,y-boxH/2,box,boxH,4);ctx.fill();ctx.stroke();
    ctx.fillStyle=name==='webapp'?'#fff':'#314a57';ctx.font=`${w<400?9:11}px Segoe UI`;ctx.textAlign='center';ctx.fillText(label,x,y+(second?-2:4));if(second){ctx.font='9px Segoe UI';ctx.fillText(second,x,y+11);}
    if(row){ctx.fillStyle=row.healthy?'#198457':'#cf2858';ctx.beginPath();ctx.arc(x+box/2-6,y-boxH/2+6,2.5,0,Math.PI*2);ctx.fill();}
  }
}

function getConfig(mode) {
  if (!$('#run-form').reportValidity()) return null;
  const experiments = [...document.querySelectorAll('input[name=experiment]:checked')].map(input=>input.value);
  if (!experiments.length) { setMessage('Select at least one registered experiment.',true); return null; }
  return { mode, engine:$('input[name=engine]:checked').value, baseline:Number($('#baseline').value), budget:Number($('#budget').value), model:$('#model').value, experiments };
}

async function command(route, payload={}) {
  if (!state?.token || pending) return null;
  pending=true;render();
  try {
    const response=await fetch(`/api/${route}`,{method:'POST',headers:{'Content-Type':'application/json','X-Dashboard-Token':state.token},body:JSON.stringify(payload),signal:AbortSignal.timeout(15000)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Command rejected.');
    if(data.message){toast(data.message);setMessage(data.message);}
    return data;
  } catch(error){setMessage(error.message,true);return null;}
  finally{pending=false;await refresh();}
}

async function start(config) {
  setMessage('Starting sandbox session...');
  const result=await command('run',config);
  if(result?.id){selectedId=result.id;chartScope=null;tab='overview';syncTabs();setMessage('Agent started.');await refresh();}
}
function syncTabs(){document.querySelectorAll('[data-tab]').forEach(button=>button.classList.toggle('selected',button.dataset.tab===tab));}
function download(artifact){if(selectedId)window.location.assign(`/api/download/${selectedId}/${artifact}`);}
$('#run-form').addEventListener('submit',event=>{event.preventDefault();const config=getConfig('preview');if(config)start(config);});
$('#execute').addEventListener('click',()=>{
  formConfig=getConfig('execute');if(!formConfig)return;
  $('#confirm-summary').textContent=`Up to ${formConfig.budget} experiments after a ${formConfig.baseline}-second baseline. Candidates: ${formConfig.experiments.map(id=>labels[id]).join(', ')}.`;
  $('#sandbox-confirm').checked=false;$('#confirm-run').disabled=true;$('#confirm').showModal();
});
$('#sandbox-confirm').addEventListener('change',()=>{$('#confirm-run').disabled=!$('#sandbox-confirm').checked;});
$('#confirm').addEventListener('close',()=>{if($('#confirm').returnValue==='execute'&&$('#sandbox-confirm').checked&&formConfig)start({...formConfig,confirmed:true});formConfig=null;});
$('#stop').addEventListener('click',()=>command('stop'));
$('#reset-stop').addEventListener('click',()=>command('reset-stop'));
$('#refresh').addEventListener('click',refresh);
$('#download').addEventListener('click',()=>download('evidence'));
$('#mobile-session').addEventListener('change',event=>{selectedId=event.target.value;chartScope=null;refresh();});
$('#session-list').addEventListener('click',event=>{const button=event.target.closest('[data-session]');if(button){selectedId=button.dataset.session;chartScope=null;refresh();}});
document.querySelector('.tabs').addEventListener('click',event=>{const button=event.target.closest('[data-tab]');if(button){tab=button.dataset.tab;syncTabs();if(state)renderView(state.selected);icons();}});
$('#view').addEventListener('change',event=>{if(event.target.id==='chart-scope'){chartScope=event.target.value;drawChart(chartData(state.selected));}});
$('#view').addEventListener('click',event=>{if(event.target.closest('#download-findings'))download('findings');});
document.querySelectorAll('input[name=engine]').forEach(input=>input.addEventListener('change',()=>{$('#model').disabled=input.value==='rules'&&input.checked;}));
window.addEventListener('resize',()=>{if(!state)return;if(tab==='overview')drawChart(chartData(state.selected));if(tab==='dependencies')drawGraph();});
icons();refresh();setInterval(()=>{if($('#live').checked)refresh();},2000);
