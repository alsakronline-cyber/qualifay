// Qualifay Agent - Options page logic
const DEFAULTS = {
  apiBase: 'http://80.225.65.148',
  agentKey: '',
  automationEnabled: false,
  pollIntervalMinutes: 2,
  log: [],
};

const $ = (id) => document.getElementById(id);

async function loadSettings() {
  const { agentSettings } = await chrome.storage.local.get('agentSettings');
  const s = { ...DEFAULTS, ...(agentSettings || {}) };
  $('apiBase').value = s.apiBase;
  $('agentKey').value = s.agentKey;
  $('automationEnabled').checked = !!s.automationEnabled;
  $('pollInterval').value = String(s.pollIntervalMinutes);
  renderLog(s.log || []);
  return s;
}

async function saveSettings(patch) {
  const { agentSettings } = await chrome.storage.local.get('agentSettings');
  const s = { ...DEFAULTS, ...(agentSettings || {}), ...patch };
  await chrome.storage.local.set({ agentSettings: s });
  chrome.runtime.sendMessage({ type: 'AGENT_SETTINGS_CHANGED' });
  return s;
}

function renderLog(log) {
  const el = $('logList');
  if (!log.length) {
    el.innerHTML = '<div class="empty">No activity yet.</div>';
    return;
  }
  el.innerHTML = log.map((entry) => {
    const time = new Date(entry.ts).toLocaleString();
    const right = entry.error
      ? `<span class="error">${escapeHtml(entry.error)}</span>`
      : `<span class="count">${entry.count} item(s)</span>`;
    return `<div class="log-item">
      <span><span class="platform">${entry.platform || '—'}</span> <span class="ts">${time}</span></span>
      ${right}
    </div>`;
  }).join('');
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function flashStatus(id, text) {
  const el = $(id);
  el.textContent = text;
  setTimeout(() => { el.textContent = ''; }, 2500);
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();

  $('btnSaveConnection').addEventListener('click', async () => {
    await saveSettings({
      apiBase: $('apiBase').value.trim().replace(/\/$/, ''),
      agentKey: $('agentKey').value.trim(),
    });
    flashStatus('connectionStatus', 'Saved ✓');
  });

  $('btnSaveAutomation').addEventListener('click', async () => {
    await saveSettings({
      automationEnabled: $('automationEnabled').checked,
      pollIntervalMinutes: Number($('pollInterval').value),
    });
    flashStatus('automationStatus', 'Saved ✓');
  });

  $('btnRefreshLog').addEventListener('click', loadSettings);
});
