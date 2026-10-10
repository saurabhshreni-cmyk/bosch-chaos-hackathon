import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';

export const validId = id => typeof id === 'string' && /^\d{8}T\d{9}Z$/.test(id);
export const experimentIds = ['workshop-crash', 'database-crash', 'workshop-delay', 'rabbitmq-crash', 'workshop-crash-with-load'];
const array = value => value == null ? [] : Array.isArray(value) ? value : [value];

export async function readJson(file) {
  try {
    if ((await stat(file)).size > 8_000_000) return null;
    return JSON.parse((await readFile(file, 'utf8')).replace(/^\uFEFF/, ''));
  } catch { return null; }
}

export function validateRun(body) {
  if (!body || Array.isArray(body) || typeof body !== 'object') throw new Error('Invalid request.');
  const keys = ['mode', 'engine', 'budget', 'baseline', 'model', 'experiments', 'confirmed'];
  if (Object.keys(body).some(key => !keys.includes(key))) throw new Error('Unsupported fields.');
  if (!['preview', 'execute'].includes(body.mode) || !['ai', 'rules'].includes(body.engine)) throw new Error('Invalid mode.');
  if (!Number.isInteger(body.budget) || body.budget < 1 || body.budget > 4) throw new Error('Budget must be 1 to 4.');
  if (!Number.isInteger(body.baseline) || body.baseline < 3 || body.baseline > 600) throw new Error('Baseline must be 3 to 600 seconds.');
  if (typeof body.model !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,99}$/.test(body.model)) throw new Error('Invalid model name.');
  if (!Array.isArray(body.experiments) || !body.experiments.length || body.experiments.length > 5 || new Set(body.experiments).size !== body.experiments.length || body.experiments.some(id => !experimentIds.includes(id))) throw new Error('Choose registered experiments.');
  if (body.mode === 'execute' && body.confirmed !== true) throw new Error('Confirm sandbox fault execution first.');
  return body;
}

export class EvidenceStore {
  constructor(root) { this.root = root; }
  file(...parts) { return path.join(this.root, ...parts); }
  async sessions() {
    let directories = [];
    try { directories = await readdir(this.file('agent', 'runs'), { withFileTypes: true }); } catch {}
    const rows = [];
    for (const dir of directories.filter(dir => dir.isDirectory() && validId(dir.name))) {
      const session = await readJson(this.file('agent', 'runs', dir.name, 'session.json'));
      if (session?.RunId === dir.name) rows.push(session);
    }
    const retained = await readJson(this.file('docs', 'evidence', 'ai-live', 'session.json'));
    if (retained && validId(retained.RunId) && !rows.some(row => row.RunId === retained.RunId)) rows.push({ ...retained, Retained: true });
    let saved = [];
    try { saved = await readdir(this.file('docs', 'evidence', 'day2'), { withFileTypes: true }); } catch {}
    for (const dir of saved.filter(dir => dir.isDirectory() && validId(dir.name))) {
      const session = await readJson(this.file('docs', 'evidence', 'day2', dir.name, 'session.json'));
      if (session?.RunId === dir.name && !rows.some(row => row.RunId === dir.name)) rows.push({ ...session, Retained: true, RetainedDay2: true });
    }
    return rows.sort((a, b) => b.RunId.localeCompare(a.RunId));
  }
  async report(id) {
    if (!validId(id)) return null;
    for (const folder of [this.file('chaos-scripts', 'results', id), this.file('docs', 'evidence', 'day2', id), this.file('docs', 'evidence', 'day1', id), this.file('docs', 'evidence', 'ai-live')]) {
      const report = await readJson(path.join(folder, 'report.json'));
      if (report?.RunId === id) return { report, analysis: await readJson(path.join(folder, 'anomalies.json')) };
    }
    return null;
  }
  async detail(session) {
    if (!session) return null;
    const directory = this.sessionDirectory(session);
    const experiments = [];
    for (const entry of array(session.Experiments)) {
      const evidence = await this.report(entry.RunId);
      const { ReportPath, AnalysisPath, ...summary } = entry;
      experiments.push({ ...summary, ...evidence });
    }
    const { Experiments, ...summary } = session;
    return {
      ...summary, Plans: array(summary.Plans), Events: array(summary.Events), experiments,
      baseline: await readJson(path.join(directory, 'baseline.json')),
      liveBaseline: await readJson(path.join(directory, 'live-baseline.json')),
      liveExperiment: await readJson(path.join(directory, 'live-experiment.json')),
    };
  }
  async download(session, artifact) {
    const directory = this.sessionDirectory(session);
    if (artifact === 'findings') return { text: await readFile(path.join(directory, 'findings.md'), 'utf8'), type: 'text/markdown', name: 'findings.md' };
    if (artifact === 'evidence') return { text: JSON.stringify(await this.detail(session), null, 2), type: 'application/json', name: 'evidence.json' };
    throw new Error('Unknown artifact.');
  }
  sessionDirectory(session) {
    if (!validId(session.RunId)) throw new Error('Invalid session ID.');
    return session.RetainedDay2 ? this.file('docs', 'evidence', 'day2', session.RunId) : session.Retained ? this.file('docs', 'evidence', 'ai-live') : this.file('agent', 'runs', session.RunId);
  }
}
