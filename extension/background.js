// Qualifay Agent - Background Service Worker
// Handles: (1) the original LeadList manual popup/sidebar messaging, and
// (2) the automated LinkedIn/Facebook agent loop — polls Qualifay for queued tasks via
// chrome.alarms, opens a background tab, waits for the content script to run, and POSTs
// the results back. No human interaction required once automation is turned on.

const AGENT_ALARM = 'qagent-poll';
const DEFAULT_SETTINGS = {
  apiBase: 'http://80.225.65.148',
  agentKey: '',
  automationEnabled: false,
  pollIntervalMinutes: 2,
  log: [], // [{ts, platform, created, error}], capped at 20
};

chrome.runtime.onInstalled.addListener(async () => {
  console.log('[Qualifay Agent] Extension installed');
  await chrome.storage.local.set({ leads: [], settings: { autoScan: true, highlightEmails: true } });
  const existing = await chrome.storage.local.get('agentSettings');
  if (!existing.agentSettings) {
    await chrome.storage.local.set({ agentSettings: DEFAULT_SETTINGS });
  }
  registerAlarm();
});

chrome.runtime.onStartup.addListener(() => {
  registerAlarm();
});

// Self-healing: onInstalled/onStartup don't fire when you click "reload" on an unpacked
// extension in chrome://extensions during development — that silently drops any existing
// chrome.alarms registration with no event to catch it. Re-registering unconditionally
// every time this script runs (which happens whenever the service worker wakes for ANY
// reason — a message, an alarm, a reload) makes the poll loop recover on its own instead
// of silently going quiet until someone notices. chrome.alarms.create is idempotent for
// the same name, so this is safe to call redundantly alongside the listeners above.
registerAlarm();

async function registerAlarm() {
  const { agentSettings } = await chrome.storage.local.get('agentSettings');
  const period = (agentSettings && agentSettings.pollIntervalMinutes) || DEFAULT_SETTINGS.pollIntervalMinutes;
  chrome.alarms.create(AGENT_ALARM, { periodInMinutes: period });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === AGENT_ALARM) pollAgentTasks().catch((e) => logAgent(null, 0, String(e)));
});

// ─── Agent automation loop ──────────────────────────────────

function buildTargetUrl(task) {
  const p = task.params || {};
  if (task.platform === 'linkedin' && task.type === 'linkedin_search') {
    const q = encodeURIComponent([p.query, p.location].filter(Boolean).join(' '));
    return `https://www.linkedin.com/search/results/people/?keywords=${q}`;
  }
  if (task.platform === 'linkedin' && task.type === 'linkedin_profile_visit' && p.profile_url) {
    return p.profile_url;
  }
  if (task.platform === 'facebook' && task.type === 'facebook_group_watch' && p.group_id) {
    return `https://www.facebook.com/groups/${encodeURIComponent(p.group_id)}`;
  }
  if (task.platform === 'facebook' && task.type === 'facebook_page_watch' && p.page_id) {
    return `https://www.facebook.com/${encodeURIComponent(p.page_id)}`;
  }
  return null;
}

async function pollAgentTasks() {
  const { agentSettings } = await chrome.storage.local.get('agentSettings');
  const settings = agentSettings || DEFAULT_SETTINGS;
  if (!settings.automationEnabled || !settings.agentKey) return;

  let resp;
  try {
    resp = await fetch(`${settings.apiBase}/api/v1/agent/tasks/next?platforms=linkedin,facebook`, {
      headers: { 'X-Agent-Key': settings.agentKey },
    });
  } catch (e) {
    await logAgent(null, 0, `poll failed: ${e}`);
    return;
  }
  if (!resp.ok) {
    await logAgent(null, 0, `poll HTTP ${resp.status}`);
    return;
  }
  const data = await resp.json();
  const task = data.task;
  if (!task) return; // nothing queued right now

  const url = buildTargetUrl(task);
  if (!url) {
    // Malformed task params — report zero results so the server doesn't wait on it.
    await postIngest(settings, task.id, task.platform, []);
    return;
  }

  const tab = await chrome.tabs.create({ url, active: false });
  await chrome.storage.local.set({ [`agentTab_${tab.id}`]: task });
}

// Wait for the tab to finish loading before messaging its content script — content
// scripts run at document_idle but SPA sites (LinkedIn/Facebook) can fire multiple
// "complete" events, so a per-tab "_messaged" flag stops us sending the task twice.
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status !== 'complete') return;
  const key = `agentTab_${tabId}`;
  const data = await chrome.storage.local.get(key);
  const task = data[key];
  if (!task || task._messaged) return;
  task._messaged = true;
  await chrome.storage.local.set({ [key]: task });
  setTimeout(() => {
    chrome.tabs.sendMessage(tabId, { type: 'RUN_AGENT_TASK', task }).catch(() => {});
  }, 800);
});

// Garbage-collect tracking if the user manually closes a tab we opened.
chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.local.remove(`agentTab_${tabId}`);
});

async function postIngest(settings, taskId, platform, items) {
  try {
    await fetch(`${settings.apiBase}/api/v1/agent/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Agent-Key': settings.agentKey },
      body: JSON.stringify({ task_id: taskId, platform, items }),
    });
    await logAgent(platform, items.length, null);
  } catch (e) {
    await logAgent(platform, 0, String(e));
  }
}

async function logAgent(platform, count, error) {
  const { agentSettings } = await chrome.storage.local.get('agentSettings');
  const settings = agentSettings || DEFAULT_SETTINGS;
  const entry = { ts: Date.now(), platform, count, error };
  settings.log = [entry, ...(settings.log || [])].slice(0, 20);
  await chrome.storage.local.set({ agentSettings: settings });
}

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'SAVE_LEAD') {
    saveLead(message.lead).then(sendResponse);
    return true;
  }
  if (message.type === 'GET_LEADS') {
    getLeads().then(sendResponse);
    return true;
  }
  if (message.type === 'CLEAR_LEADS') {
    clearLeads().then(sendResponse);
    return true;
  }
  if (message.type === 'DELETE_LEAD') {
    deleteLead(message.id).then(sendResponse);
    return true;
  }
  if (message.type === 'GET_SETTINGS') {
    getSettings().then(sendResponse);
    return true;
  }
  if (message.type === 'SAVE_SETTINGS') {
    saveSettings(message.settings).then(sendResponse);
    return true;
  }
  if (message.type === 'EXPORT_LEADS') {
    getLeads().then(leads => sendResponse({ leads }));
    return true;
  }
  if (message.type === 'OPEN_SIDEBAR') {
    chrome.tabs.sendMessage(sender.tab.id, { type: 'TOGGLE_SIDEBAR' });
    sendResponse({ ok: true });
    return true;
  }
  if (message.type === 'AGENT_SCRAPE_RESULT') {
    (async () => {
      const { agentSettings } = await chrome.storage.local.get('agentSettings');
      const settings = agentSettings || DEFAULT_SETTINGS;
      await postIngest(settings, message.taskId, message.platform, message.items || []);
      const tabId = sender.tab && sender.tab.id;
      if (tabId) {
        await chrome.storage.local.remove(`agentTab_${tabId}`);
        chrome.tabs.remove(tabId).catch(() => {});
      }
      sendResponse({ ok: true });
    })();
    return true;
  }
  if (message.type === 'AGENT_SETTINGS_CHANGED') {
    registerAlarm();
    sendResponse({ ok: true });
    return true;
  }
});

async function saveLead(lead) {
  const data = await chrome.storage.local.get('leads');
  const leads = data.leads || [];
  const existing = leads.findIndex(l => l.profileUrl === lead.profileUrl);
  if (existing >= 0) {
    leads[existing] = { ...leads[existing], ...lead, updatedAt: Date.now() };
  } else {
    leads.unshift({ ...lead, id: crypto.randomUUID(), savedAt: Date.now() });
  }
  await chrome.storage.local.set({ leads });
  return { ok: true, count: leads.length };
}

async function getLeads() {
  const data = await chrome.storage.local.get('leads');
  return data.leads || [];
}

async function clearLeads() {
  await chrome.storage.local.set({ leads: [] });
  return { ok: true };
}

async function deleteLead(id) {
  const data = await chrome.storage.local.get('leads');
  const leads = (data.leads || []).filter(l => l.id !== id);
  await chrome.storage.local.set({ leads });
  return { ok: true };
}

async function getSettings() {
  const data = await chrome.storage.local.get('settings');
  return data.settings || { autoScan: true, highlightEmails: true };
}

async function saveSettings(settings) {
  await chrome.storage.local.set({ settings });
  return { ok: true };
}
