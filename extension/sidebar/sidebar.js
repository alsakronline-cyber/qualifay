// LeadList - Sidebar Logic
'use strict';

let allLeads = [];
let currentTab = 'scrape';
let currentPageType = 'other';

// ── Messaging ──────────────────────────────────────────────────────────────
function postToContent(action, payload = {}) {
  window.parent.postMessage({ source: 'leadlist-sidebar', action, payload }, '*');
}

window.addEventListener('message', (e) => {
  if (e.data?.source !== 'leadlist-content') return;
  const { action, payload } = e.data;
  if (action === 'PAGE_CHANGED') onPageChanged(payload);
  if (action === 'SCRAPE_RESULT') onScrapeResult(payload);
  if (action === 'LEADS_DATA') onLeadsData(payload.leads);
});

// ── Page changed ───────────────────────────────────────────────────────────
function onPageChanged({ url, pageType }) {
  currentPageType = pageType;
  const badge = document.getElementById('pageBadge');
  const urlEl = document.getElementById('pageUrl');
  badge.className = 'page-badge ' + (pageType === 'profile' ? 'profile' : pageType.includes('search') ? 'search' : 'other');
  badge.textContent = pageType === 'profile' ? 'Profile' : pageType.includes('search') ? 'Search' : 'Other';
  if (urlEl) urlEl.textContent = url.replace('https://www.linkedin.com', '');
  resetScrapeState();
}

// ── Scrape result ──────────────────────────────────────────────────────────
function onScrapeResult({ type, lead, leads }) {
  const btn = document.getElementById('btnScrape');
  btn.disabled = false;
  btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/><path d="M21 21l-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg> Extract Contacts`;

  if (type === 'profile' && lead) {
    setStatus('found', lead.emails.length + lead.phones.length > 0 ? `Found ${lead.emails.length} email(s), ${lead.phones.length} phone(s)` : 'No contacts found on this profile');
    renderProfileResult(lead);
    refreshLeadsCount();
  } else if (type === 'search' && leads) {
    setStatus('found', `Found ${leads.length} profiles on page`);
    renderSearchResult(leads);
    refreshLeadsCount();
  } else {
    setStatus('error', 'Navigate to a LinkedIn profile or search page');
  }
}

function renderProfileResult(lead) {
  document.getElementById('scrapeResult').style.display = 'block';
  document.getElementById('searchResult').style.display = 'none';

  const avatarEl = document.getElementById('resultAvatar');
  if (lead.avatar) {
    avatarEl.innerHTML = `<img src="${lead.avatar}" alt="${lead.name}"/>`;
  } else {
    avatarEl.textContent = (lead.name || '?').charAt(0).toUpperCase();
  }
  document.getElementById('resultName').textContent = lead.name || 'Unknown';
  document.getElementById('resultTitle').textContent = lead.title || '—';
  document.getElementById('resultCompany').textContent = lead.company || '';

  const list = document.getElementById('contactList');
  list.innerHTML = '';

  if (!lead.emails.length && !lead.phones.length) {
    list.innerHTML = '<div class="no-contact">⚠️ No contact info visible on this profile</div>';
    return;
  }

  lead.emails.forEach(email => {
    list.appendChild(makeContactRow('email', email, 'Email'));
  });
  lead.phones.forEach(phone => {
    list.appendChild(makeContactRow('phone', phone, 'Phone'));
  });
}

function makeContactRow(type, value, label) {
  const row = document.createElement('div');
  row.className = 'contact-row';
  const iconSvg = type === 'email'
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><rect x="2" y="4" width="20" height="16" rx="2" stroke="#3b82f6" stroke-width="2"/><path d="M2 8l10 6 10-6" stroke="#3b82f6" stroke-width="2"/></svg>`
    : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6.6 10.8a15.2 15.2 0 006.6 6.6l2.2-2.2a1 1 0 011-.24 11.4 11.4 0 003.57.57 1 1 0 011 1V20a1 1 0 01-1 1A17 17 0 013 4a1 1 0 011-1h3.5a1 1 0 011 1 11.4 11.4 0 00.57 3.57 1 1 0 01-.25 1L6.6 10.8z" stroke="#10b981" stroke-width="2"/></svg>`;
  row.innerHTML = `
    <div class="contact-icon ${type}">${iconSvg}</div>
    <span class="contact-value" title="${value}">${value}</span>
    <span class="contact-tag found">${label}</span>
    <button class="btn-copy-val" data-value="${value}" title="Copy">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="2"/></svg>
    </button>`;
  row.querySelector('.btn-copy-val').addEventListener('click', (e) => {
    navigator.clipboard.writeText(value).then(() => showToast('Copied!', 'success'));
    e.stopPropagation();
  });
  return row;
}

function renderSearchResult(leads) {
  document.getElementById('scrapeResult').style.display = 'none';
  const panel = document.getElementById('searchResult');
  panel.style.display = 'block';
  document.getElementById('searchResultTitle').textContent = `Found ${leads.length} profiles — saved to Leads`;
  const list = document.getElementById('searchResultList');
  list.innerHTML = '';
  leads.slice(0, 8).forEach(l => {
    const d = document.createElement('div');
    d.style.cssText = 'padding:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:9px;margin-bottom:6px;font-size:11px;color:#94a3b8';
    const sub = [l.title, l.company].filter(Boolean).join(' · ') || '—';
    d.innerHTML = `<div style="font-weight:600;color:#e2e8f0;margin-bottom:2px">${l.name}</div><div>${sub}</div>`;
    list.appendChild(d);
  });
}

// ── Leads tab ──────────────────────────────────────────────────────────────
function onLeadsData(leads) {
  allLeads = leads || [];
  renderLeadsList(allLeads);
  refreshLeadsCount();
}

function renderLeadsList(leads) {
  const list = document.getElementById('leadsList');
  document.getElementById('showingCount').textContent = leads.length;
  document.getElementById('totalCount').textContent = allLeads.length;

  if (!leads.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" stroke="#0D6EFD" stroke-width="2"/><circle cx="9" cy="7" r="4" stroke="#0D6EFD" stroke-width="2"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" stroke="#0D6EFD" stroke-width="2" stroke-linecap="round"/></svg>
        </div>
        <h3>No leads yet</h3>
        <p>Go to a LinkedIn profile or search page and click <strong>Extract Contacts</strong></p>
      </div>`;
    return;
  }

  list.innerHTML = '';
  leads.forEach(lead => list.appendChild(makeLeadRow(lead)));
}

function makeLeadRow(lead) {
  const row = document.createElement('div');
  row.className = 'lead-row';
  const initials = (lead.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  const chips = [
    ...(lead.emails || []).slice(0, 2).map(e => `<span class="chip email"><span class="chip-dot"></span>${e}</span>`),
    ...(lead.phones || []).slice(0, 1).map(p => `<span class="chip phone"><span class="chip-dot"></span>${p}</span>`)
  ].join('');

  row.innerHTML = `
    <div class="lead-row-header">
      <div class="lead-row-avatar">${initials}</div>
      <div style="flex:1;overflow:hidden">
        <div class="lead-row-name">${lead.name || 'Unknown'}</div>
        <div class="lead-row-sub">${[lead.title, lead.company].filter(Boolean).join(' · ')}</div>
      </div>
    </div>
    <div class="lead-chips">${chips || '<span style="font-size:10px;color:#475569">No contact data</span>'}</div>
    <button class="lead-row-delete" data-id="${lead.id}" title="Delete">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>`;

  row.querySelector('.lead-row-delete').addEventListener('click', (e) => {
    e.stopPropagation();
    postToContent('DELETE_LEAD', { id: lead.id });
    showToast('Lead deleted', 'success');
  });
  row.addEventListener('click', () => {
    if (lead.profileUrl) window.open(lead.profileUrl, '_blank');
  });
  return row;
}

function refreshLeadsCount() {
  postToContent('GET_LEADS');
}

// ── Tabs ───────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    currentTab = tab.dataset.tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panelScrape').style.display = currentTab === 'scrape' ? 'block' : 'none';
    const panelLeads = document.getElementById('panelLeads');
    if (currentTab === 'leads') {
      panelLeads.style.display = 'flex';
      postToContent('GET_LEADS');
    } else {
      panelLeads.style.display = 'none';
    }
  });
});

// ── Scrape button ──────────────────────────────────────────────────────────
document.getElementById('btnScrape').addEventListener('click', () => {
  const btn = document.getElementById('btnScrape');
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> Scanning…`;
  setStatus('scanning', 'Scanning page for contacts…');
  postToContent('SCRAPE_CURRENT');
});

// ── Search filter ──────────────────────────────────────────────────────────
document.getElementById('searchInput').addEventListener('input', (e) => {
  const q = e.target.value.toLowerCase();
  if (!q) return renderLeadsList(allLeads);
  const filtered = allLeads.filter(l =>
    (l.name || '').toLowerCase().includes(q) ||
    (l.company || '').toLowerCase().includes(q) ||
    (l.emails || []).some(em => em.toLowerCase().includes(q)) ||
    (l.phones || []).some(p => p.includes(q))
  );
  renderLeadsList(filtered);
});

// ── Export ─────────────────────────────────────────────────────────────────
document.getElementById('btnExportCsv').addEventListener('click', () => { postToContent('EXPORT_CSV'); showToast('CSV download started!', 'success'); });
document.getElementById('btnCsvExport').addEventListener('click', () => { postToContent('EXPORT_CSV'); showToast('CSV download started!', 'success'); });
document.getElementById('btnJsonExport').addEventListener('click', () => { postToContent('EXPORT_JSON'); showToast('JSON download started!', 'success'); });

// ── Clear ──────────────────────────────────────────────────────────────────
document.getElementById('btnClear').addEventListener('click', () => {
  if (confirm('Clear all saved leads?')) {
    postToContent('CLEAR_LEADS');
    showToast('All leads cleared', 'success');
  }
});

// ── Close ──────────────────────────────────────────────────────────────────
document.getElementById('btnClose').addEventListener('click', () => postToContent('CLOSE_SIDEBAR'));

// ── Helpers ────────────────────────────────────────────────────────────────
function setStatus(type, text) {
  const dot = document.getElementById('statusDot');
  dot.className = 'status-dot ' + type;
  document.getElementById('statusText').textContent = text;
}

function resetScrapeState() {
  setStatus('', 'Ready to scan');
  document.getElementById('scrapeResult').style.display = 'none';
  document.getElementById('searchResult').style.display = 'none';
  const btn = document.getElementById('btnScrape');
  btn.disabled = false;
  btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/><path d="M21 21l-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg> Extract Contacts`;
}

let toastTimer;
function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast ' + type; }, 2500);
}

// ── Init ───────────────────────────────────────────────────────────────────
postToContent('GET_LEADS');
