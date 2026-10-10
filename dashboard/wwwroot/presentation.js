// Shared presentation rules. No model calls or experiment execution.
const dashboardPresentation = (() => {
  function escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, c =>
      ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  }
  function escapeTree(value) {
    if (typeof value === 'string') return escape(value);
    if (Array.isArray(value)) return value.map(escapeTree);
    if (value && typeof value === 'object')
      return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, escapeTree(v)]));
    return value;
  }
  function summary(state) {
    const services = state.services || [], modules = state.modules || [];
    return {
      running: services.filter(s => s.running).length,
      services: services.length,
      healthy: services.filter(s => s.running && s.health === 'healthy').length,
      unmeasured: services.filter(s => s.running && !['healthy','unhealthy','starting'].includes(s.health)).length,
      modulesHealthy: modules.filter(m => m.healthy).length,
      modules: modules.length,
      runs: (state.runs || []).length,
      active: !!state.run?.isRunning,
      stop: !!state.killSwitchEngaged,
    };
  }
  function validateExperiment(exp, duration, delay) {
    if (!Number.isInteger(duration) || duration < exp.minDuration || duration > exp.maxDuration)
      return 'Duration must be an integer between ' + exp.minDuration + ' and ' + exp.maxDuration + ' seconds.';
    if (exp.supportsDelay && (!Number.isInteger(delay) || delay < exp.minDelayMs || delay > exp.maxDelayMs))
      return 'Delay must be an integer between ' + exp.minDelayMs + ' and ' + exp.maxDelayMs + ' milliseconds.';
    return null;
  }
  return { escape, escapeTree, summary, validateExperiment };
})();
if (typeof module !== 'undefined') module.exports = dashboardPresentation;
