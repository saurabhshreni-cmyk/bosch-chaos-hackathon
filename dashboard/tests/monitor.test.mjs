import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { FailureMonitor } from '../monitor.mjs';

const services = ['webapp', 'customermanagementapi', 'vehiclemanagementapi', 'workshopmanagementapi', 'sqlserver', 'rabbitmq'];
function health(n, { bad = false, latency = 50, database = false, dockerError = null } = {}) {
  const checked = new Date(Date.UTC(2026, 9, 10, 12, 0, n * 5)).toISOString();
  return { checked, dockerError, modules: ['CustomerManagement', 'VehicleManagement', 'WorkshopManagement'].map(name => ({ name, checked, healthy: !(bad && name === 'WorkshopManagement'), status: 200, latency: name === 'WorkshopManagement' ? latency : 50, failureMode: bad && name === 'WorkshopManagement' ? 'Offline fallback' : null })),
    containers: services.map(service => ({ service, state: database && service === 'sqlserver' ? 'exited' : 'running', health: null })) };
}
async function fixture(fn, extra = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'pitstop-monitor-test-'));
  const monitor = new FailureMonitor({ root, ai: false, ...extra });
  try { await monitor.load(); await fn(monitor, root); }
  finally { monitor.close(); await rm(root, { recursive: true, force: true }); }
}
const validAi = options => {
  const fields = JSON.parse(options.body).format.properties;
  return { ok: true, json: async () => ({ response: JSON.stringify({ explanation: fields.explanation.enum[0], possibleCause: fields.possibleCause.enum[0], solutions: fields.solutions.items.enum.slice(0, 2) }) }) };
};

test('two failures confirm an incident, two healthy probes verify recovery and restart retains it', async () => fixture(async (monitor, root) => {
  await monitor.observe(health(0, { bad: true })); assert.equal(monitor.incidents.length, 0);
  await monitor.observe(health(1, { bad: true })); assert.equal(monitor.incidents.length, 1);
  const incident = monitor.incidents[0]; assert.equal(incident.kind, 'Page unavailable');
  assert.equal(incident.observations.length, 2);
  assert.equal(incident.firstObserved, health(0).checked);
  await monitor.observe(health(2, { bad: true })); assert.equal(monitor.incidents.length, 1);
  await monitor.observe(health(3)); assert.equal(incident.status, 'Active');
  await monitor.observe(health(4)); assert.equal(incident.status, 'Recovered');
  assert.equal(incident.durationSeconds, 20); assert.equal(monitor.events.length, 2);
  assert.equal(JSON.parse(await readFile(monitor.file, 'utf8')).incidents[0].status, 'Recovered');
  const restored = new FailureMonitor({ root, ai: false }); await restored.load();
  assert.equal(restored.incidents[0].status, 'Recovered'); restored.close();
}));

test('offline HTTP 200 is a failure; shared dependency is a hypothesis, not invented root cause', async () => fixture(async monitor => {
  await monitor.observe(health(0, { bad: true, database: true }), { experimentActive: true });
  await monitor.observe(health(1, { bad: true, database: true }), { experimentActive: true });
  const page = monitor.incidents.find(item => item.subject === 'WorkshopManagement');
  assert.match(page.diagnosis.cause, /sqlserver/); assert.match(page.diagnosis.cause, /does not prove/);
  assert.match(page.context, /experiment active/); assert.equal(page.observations[0].status, 200);
  assert.ok(monitor.incidents.some(item => item.subject === 'sqlserver'));
}));

test('latency learning excludes faults and experiment traffic, requires baseline and debounces regression', async () => fixture(async monitor => {
  for (let n = 0; n < 6; n++) await monitor.observe(health(n));
  await monitor.observe(health(6, { latency: 900 })); assert.equal(monitor.incidents.length, 0);
  await monitor.observe(health(7, { latency: 900 })); assert.equal(monitor.incidents[0].kind, 'Latency regression');
  assert.equal(monitor.baselines.get('WorkshopManagement').length, 6);
  await monitor.observe(health(8, { bad: true }));
  await monitor.observe(health(9, { bad: true }));
  assert.equal(monitor.incidents.find(item => item.kind === 'Latency regression').status, 'Active');
  await monitor.observe(health(10), { experimentActive: true });
  await monitor.observe(health(11), { experimentActive: true });
  assert.equal(monitor.baselines.get('WorkshopManagement').length, 6);
  assert.ok(monitor.incidents.every(item => item.status === 'Recovered'));
}));

test('Docker unavailable does not fabricate missing-container failures or recover existing ones', async () => fixture(async monitor => {
  await monitor.observe(health(0, { database: true })); await monitor.observe(health(1, { database: true }));
  const outage = { ...health(2), containers: [], dockerError: 'Unavailable' };
  await monitor.observe(outage); await monitor.observe({ ...outage, checked: health(3).checked });
  assert.equal(monitor.incidents.length, 1); assert.equal(monitor.incidents[0].status, 'Active');
}));

test('a missing core container is detected, explained and recovered only on valid inventory', async () => fixture(async monitor => {
  const missing = n => ({ ...health(n), containers: health(n).containers.filter(row => row.service !== 'sqlserver') });
  await monitor.observe(missing(0)); await monitor.observe(missing(1));
  assert.equal(monitor.incidents.length, 1); assert.match(monitor.incidents[0].diagnosis.cause, /sqlserver is missing/);
  await monitor.observe(health(2)); await monitor.observe(health(3));
  assert.equal(monitor.incidents[0].status, 'Recovered');
}));

test('AI cannot substitute invented facts even with valid JSON field names', async () => fixture(async monitor => {
  await monitor.observe(health(0, { bad: true })); await monitor.observe(health(1, { bad: true }));
  await monitor.analyze(true); assert.match(monitor.incidents[0].ai.status, /Unavailable/);
}, { ai: true, fetcher: async () => ({ ok: true, json: async () => ({ response: JSON.stringify({ explanation: 'The agent crashed.', possibleCause: 'Data was lost.', solutions: ['Delete the database.'] }) }) }) }));

test('active incident on restart awaits verification, does not silently recover', async () => fixture(async (monitor, root) => {
  await monitor.observe(health(0, { bad: true })); await monitor.observe(health(1, { bad: true }));
  const restored = new FailureMonitor({ root, ai: false }); await restored.load();
  assert.equal(restored.incidents[0].status, 'Awaiting verification');
  await restored.observe(health(2)); assert.equal(restored.incidents[0].status, 'Awaiting verification');
  await restored.observe(health(3)); assert.equal(restored.incidents[0].status, 'Recovered'); restored.close();
}));

test('local AI is schema validated and never executes actions', async () => fixture(async monitor => {
  await monitor.observe(health(0, { bad: true })); await monitor.observe(health(1, { bad: true }));
  await monitor.analyze(true);
  assert.equal(monitor.incidents[0].ai.status, 'Completed');
  assert.match(monitor.incidents[0].ai.caveat, /not a confirmed/);
}, { ai: true, fetcher: async (url, options) => {
  assert.equal(url, 'http://127.0.0.1:11434/api/generate');
  assert.equal(JSON.parse(options.body).stream, false);
  return validAi(options);
} }));

test('invalid AI output preserves deterministic diagnosis', async () => fixture(async monitor => {
  await monitor.observe(health(0, { bad: true })); await monitor.observe(health(1, { bad: true }));
  await monitor.analyze(true); assert.match(monitor.incidents[0].ai.status, /Unavailable/);
  assert.ok(monitor.incidents[0].diagnosis.solutions.length);
}, { ai: true, fetcher: async () => ({ ok: true, json: async () => ({ response: '{"command":"docker kill sqlserver"}' }) }) }));

test('recovered incidents still receive optional AI explanations after experiment activity ends', async () => fixture(async monitor => {
  await monitor.observe(health(0, { bad: true }), { experimentActive: true });
  await monitor.observe(health(1, { bad: true }), { experimentActive: true });
  await monitor.observe(health(2)); await monitor.observe(health(3));
  assert.equal(monitor.incidents[0].status, 'Recovered'); assert.equal(monitor.incidents[0].ai.status, 'Queued');
  await monitor.analyze(true); assert.equal(monitor.incidents[0].ai.status, 'Completed');
}, { ai: true, fetcher: async (url, options) => validAi(options) }));
