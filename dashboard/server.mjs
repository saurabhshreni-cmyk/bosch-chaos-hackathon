import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { readFile, mkdir, writeFile, unlink, access, appendFile } from 'node:fs/promises';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { EvidenceStore, readJson, validId, validateRun } from './store.mjs';

const directory = path.dirname(fileURLToPath(import.meta.url));
const exec = promisify(execFile);
const exists = async file => { try { await access(file); return true; } catch { return false; } };
const now = () => new Date().toISOString();
const runId = () => now().replace(/[-:.]/g, '');

async function dockerPath() {
  const executable = process.platform === 'win32' ? 'docker.exe' : 'docker';
  const searchPath = Object.entries(process.env).find(([key]) => key.toLowerCase() === 'path')?.[1] || '';
  const directories = searchPath.split(path.delimiter);
  if (process.platform === 'win32') directories.push(
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'DockerDesktop', 'resources', 'bin'),
    path.join(process.env.ProgramFiles || 'C:/Program Files', 'Docker', 'Docker', 'resources', 'bin')
  );
  for (const folder of directories.filter(Boolean)) {
    const candidate = path.join(folder, executable);
    if (await exists(candidate)) return candidate;
  }
  throw new Error('Docker executable not found.');
}

function childEnvironment(docker) {
  const entries = Object.entries(process.env);
  const searchPath = entries.find(([key]) => key.toLowerCase() === 'path')?.[1] || '';
  return { ...Object.fromEntries(entries.filter(([key]) => key.toLowerCase() !== 'path')), PATH: `${path.dirname(docker)}${path.delimiter}${searchPath}` };
}

export function createDashboard({ root = path.dirname(directory), controls = true, probes = true } = {}) {
  const store = new EvidenceStore(root);
  const token = randomBytes(32).toString('hex');
  const stopFile = store.file('chaos-scripts', 'STOP');
  let job = null;
  let lockState = { Agent: false, Experiment: false, checked: null, error: null };
  let lockPending = null;
  let health = { modules: [], containers: [], model: { available: false, models: [] }, checked: null };
  let healthPending = null;

  async function locks(fresh = false) {
    if (!probes) return lockState;
    if (!fresh && lockState.checked && Date.now() - Date.parse(lockState.checked) < 5000) return lockState;
    if (lockPending) return lockPending;
    lockPending = (async () => {
      try {
        const { stdout } = await exec('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(directory, 'check-locks.ps1')], { windowsHide: true, timeout: 8000 });
        lockState = { ...JSON.parse(stdout.replace(/^\uFEFF/, '')), checked: now(), error: null };
      } catch (error) { lockState = { Agent: true, Experiment: true, checked: now(), error: 'Cannot verify the sandbox locks.' }; }
      return lockState;
    })().finally(() => { lockPending = null; });
    return lockPending;
  }

  async function refreshHealth() {
    if (!probes || healthPending || health.checked && Date.now() - Date.parse(health.checked) < 5000) return;
    healthPending = (async () => {
      const modules = await Promise.all(['CustomerManagement', 'VehicleManagement', 'WorkshopManagement'].map(async name => {
        const started = performance.now();
        try {
          const response = await fetch(`http://127.0.0.1:7005/${name}`, { signal: AbortSignal.timeout(2000) });
          const content = await response.text();
          const healthy = response.status === 200 && !/module is offline|management\s*-\s*offline/i.test(content) && content.includes(name.replace('Management', ' Management'));
          return { name, healthy, status: response.status, latency: Math.round(performance.now() - started), checked: now() };
        } catch { return { name, healthy: false, status: null, latency: Math.round(performance.now() - started), checked: now(), timeout: true }; }
      }));
      let model = { available: false, models: [] };
      try {
        const response = await fetch('http://127.0.0.1:11434/api/tags', { signal: AbortSignal.timeout(2000) });
        const data = await response.json();
        model = { available: response.ok, models: (data.models ?? []).map(item => item.name) };
      } catch {}
      let containers = [], dockerError = null;
      try {
        const { stdout } = await exec(await dockerPath(), ['compose', '-f', store.file('src', 'docker-compose.yml'), 'ps', '--all', '--format', 'json'], { windowsHide: true, timeout: 6000, maxBuffer: 500_000 });
        const trimmed = stdout.trim();
        const parsed = trimmed.startsWith('[') ? JSON.parse(trimmed) : trimmed ? trimmed.split(/\r?\n/).map(line => JSON.parse(line)) : [];
        containers = parsed.map(row => ({ service: row.Service, state: row.State, health: row.Health || null }));
      } catch { dockerError = 'Docker status unavailable'; }
      health = { modules, containers, model, checked: now(), dockerError };
    })().finally(() => { healthPending = null; });
  }

  const server = http.createServer(async (request, response) => {
    const send = (status, value, type = 'application/json') => {
      response.writeHead(status, { 'Content-Type': `${type}; charset=utf-8`, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" });
      response.end(type === 'application/json' ? JSON.stringify(value) : value);
    };
    try {
      const port = server.address()?.port;
      const hosts = [`127.0.0.1:${port}`, `localhost:${port}`];
      if (!hosts.includes(request.headers.host)) return send(403, { error: 'Localhost requests only.' });
      const url = new URL(request.url, `http://${request.headers.host}`);
      if (request.method === 'POST') {
        if (!controls) return send(403, { error: 'Dashboard is read-only.' });
        if (!hosts.map(host => `http://${host}`).includes(request.headers.origin) || request.headers['x-dashboard-token'] !== token || !request.headers['content-type']?.startsWith('application/json')) return send(403, { error: 'Request validation failed.' });
        let body = '';
        for await (const chunk of request) { body += chunk; if (body.length > 4096) return send(413, { error: 'Request too large.' }); }
        const payload = JSON.parse(body || '{}');
        if (url.pathname === '/api/stop') {
          await writeFile(stopFile, 'Dashboard emergency stop\n', { flag: 'w' });
          return send(200, { message: 'STOP requested. The runner restores between bounded probes; an AI request may finish first.' });
        }
        if (url.pathname === '/api/reset-stop') {
          const status = await locks(true);
          if (job?.running || status.Agent || status.Experiment || status.error) return send(409, { error: 'Wait for the agent and experiment to finish before clearing STOP.' });
          try { await unlink(stopFile); } catch (error) { if (error.code !== 'ENOENT') throw error; }
          return send(200, { message: 'STOP cleared.' });
        }
        if (url.pathname === '/api/run') {
          const config = validateRun(payload);
          if (job?.running) return send(409, { error: 'A dashboard session is already running.' });
          job = { id: runId(), running: true, stage: 'Checking sandbox', log: [], started: now(), exitCode: null };
          try {
            const status = await locks(true);
            if (status.Agent || status.Experiment || status.error) throw new Error('An agent or experiment is active, or locks cannot be verified.');
            if (await exists(stopFile)) throw new Error('STOP is active. Clear it after recovery before starting another session.');
            const current = job;
            const runtime = path.join(directory, 'runtime');
            await mkdir(runtime, { recursive: true });
            const args = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(directory, 'launch-agent.ps1'), '-Mode', config.mode, '-Engine', config.engine, '-Budget', String(config.budget), '-Baseline', String(config.baseline), '-Model', config.model, '-SessionId', current.id, '-Experiments', config.experiments.join(',')];
            const docker = await dockerPath();
            const child = spawn('powershell.exe', args, { cwd: root, windowsHide: true, shell: false, env: childEnvironment(docker) });
            current.stage = 'Starting';
            let remainder = '';
            const record = data => {
              const text = data.toString().replace(/\u001b\[[0-9;]*m/g, '');
              void appendFile(path.join(runtime, `${current.id}.log`), text).catch(() => {});
              const lines = (remainder + text).split(/\r?\n/); remainder = lines.pop();
              current.log.push(...lines.filter(Boolean).map(text => ({ at: now(), text: text.slice(0, 1000) })));
              current.log = current.log.slice(-150);
            };
            child.stdout.on('data', record); child.stderr.on('data', record);
            child.on('error', error => { current.log.push({ at: now(), text: error.message }); current.running = false; current.exitCode = -1; });
            child.on('close', code => { if (remainder) current.log.push({ at: now(), text: remainder }); current.running = false; current.exitCode = code; current.stage = code === 0 ? 'Finished' : 'Stopped with error'; });
            return send(202, { id: current.id });
          } catch (error) { job.running = false; job.stage = 'Rejected'; job.log.push({ at: now(), text: error.message }); return send(409, { error: error.message }); }
        }
        return send(404, { error: 'Unknown command.' });
      }
      if (request.method !== 'GET') return send(405, { error: 'Method not allowed.' });
      if (url.pathname === '/api/state') {
        void refreshHealth(); void locks();
        const sessions = await store.sessions();
        const selected = url.searchParams.get('session');
        if (selected && !validId(selected)) return send(400, { error: 'Invalid session ID.' });
        const session = selected ? sessions.find(item => item.RunId === selected) : sessions[0];
        const detail = await store.detail(session);
        return send(200, { token, controls, now: now(), stop: await exists(stopFile), locks: lockState, health, job, sessions: sessions.slice(0, 80).map(item => ({ id: item.RunId, stage: item.Stage, mode: item.Mode, execute: item.Execute, count: (item.Experiments ?? []).length, retained: !!item.Retained })), selected: detail, dependencies: await readJson(store.file('agent', 'dependencies.json')), catalog: await readJson(store.file('agent', 'experiments.json')) });
      }
      if (url.pathname.startsWith('/api/download/')) {
        const parts = url.pathname.split('/');
        if (parts.length !== 5 || !validId(parts[3])) return send(400, { error: 'Invalid artifact request.' });
        const session = (await store.sessions()).find(item => item.RunId === parts[3]);
        if (!session) return send(404, { error: 'Session not found.' });
        try {
          const artifact = await store.download(session, parts[4]);
          response.setHeader('Content-Disposition', `attachment; filename="${parts[3]}-${artifact.name}"`);
          return send(200, artifact.text, artifact.type);
        } catch { return send(404, { error: 'Artifact not available yet.' }); }
      }
      const staticFiles = {
        '/': ['public/index.html', 'text/html'], '/app.js': ['public/app.js', 'text/javascript'], '/styles.css': ['public/styles.css', 'text/css'],
        '/lucide.js': ['node_modules/lucide/dist/umd/lucide.js', 'text/javascript'],
      };
      if (url.pathname === '/garage.png') {
        const bitmap = await readFile(store.file('pitstop-garage.png'));
        response.writeHead(200, { 'Content-Type': 'image/png', 'X-Content-Type-Options': 'nosniff' }); return response.end(bitmap);
      }
      const file = staticFiles[url.pathname];
      if (!file) return send(404, { error: 'Not found.' });
      send(200, await readFile(path.join(directory, file[0]), 'utf8'), file[1]);
    } catch (error) { send(400, { error: error instanceof SyntaxError ? 'Invalid JSON.' : 'Request could not be completed.' }); }
  });
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createDashboard({ controls: process.env.DASHBOARD_READ_ONLY !== '1' });
  const firstPort = Number(process.env.PORT || 7010);
  let port = firstPort;
  server.on('error', error => {
    if (error.code === 'EADDRINUSE' && port < firstPort + 10) server.listen(++port, '127.0.0.1');
    else { console.error(error.message); process.exitCode = 1; }
  });
  server.on('listening', () => console.log(`Pitstop Chaos Dashboard: http://127.0.0.1:${server.address().port}`));
  server.listen(port, '127.0.0.1');
}
