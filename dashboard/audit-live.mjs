import { writeFile } from 'node:fs/promises';
import { setTimeout } from 'node:timers/promises';
import { validId } from './store.mjs';

const id = process.argv[2];
if (!validId(id)) throw new Error('Supply the existing session ID to observe; this script never starts experiments.');
const observations = [];
const started = new Date().toISOString();
const deadline = Date.now() + 15 * 60_000;
let final, error;
try {
  while (Date.now() < deadline) {
    const response = await fetch(`http://127.0.0.1:7010/api/state?session=${id}`, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error(`Dashboard returned ${response.status}`);
    const state = await response.json();
    final = state;
    const session = state.selected;
    observations.push({ at: new Date().toISOString(), stage: session?.Stage,
      liveStage: session?.liveExperiment?.Stage, locks: state.locks,
      modules: state.health.modules, containers: state.health.containers,
      incidents: state.monitor.incidents.map(({ id, subject, kind, status, detected, recovered }) => ({ id, subject, kind, status, detected, recovered })) });
    if (session?.Stage === 'Stopped with error') throw new Error(session.Error || 'Agent stopped with error');
    if (session?.Stage === 'Completed' && !state.locks.Agent && !state.locks.Experiment &&
        state.health.modules.length === 3 && state.health.modules.every(row => row.healthy) &&
        !state.monitor.incidents.some(item => item.status !== 'Recovered')) break;
    await setTimeout(3000);
  }
  if (final?.selected?.Stage !== 'Completed') throw new Error('Timed out waiting for a completed agent run.');
} catch (failure) { error = failure.message; }
const experiments = final?.selected?.experiments || [];
const checks = {
  agentCompleted: final?.selected?.Stage === 'Completed',
  threeExperimentsRecovered: experiments.length === 3 && experiments.every(row => row.Recovered),
  threeFailureCategories: new Set(experiments.map(row => row.Category)).size >= 3,
  allAnalysesCompleted: experiments.length > 0 && experiments.every(row => row.AiStatus?.startsWith('Completed')),
  liveSnapshotsObserved: observations.some(row => row.liveStage),
  failedPageObserved: observations.some(row => row.modules.some(module => !module.healthy)),
  automaticIncidentObserved: observations.some(row => row.incidents.some(item => item.status === 'Active')),
  finalHealthy: final?.health.modules.length === 3 && final.health.modules.every(row => row.healthy),
  monitorRecovered: final?.monitor.enabled && !final.monitor.error && final.monitor.incidents.every(item => item.status === 'Recovered'),
  noRemainingLocks: final?.locks.error === null && !final?.locks.Agent && !final?.locks.Experiment,
};
const result = { started, finished: new Date().toISOString(), session: id,
  passed: !error && Object.values(checks).every(Boolean), error: error || null, checks,
  experiments: experiments.map(({ ExperimentId, RunId, Recovered, AiStatus, RecoverySeconds, RollbackReason }) => ({ ExperimentId, RunId, Recovered, AiStatus, RecoverySeconds, RollbackReason })), observations };
await writeFile(new URL('../submission/runtime-audit.json', import.meta.url), JSON.stringify(result, null, 2));
console.log(JSON.stringify({ ...result, observations: `${observations.length} retained snapshots` }, null, 2));
if (!result.passed) process.exitCode = 1;
