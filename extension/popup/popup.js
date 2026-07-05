// LeadList - Popup Logic
'use strict';

async function getLeads() {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'GET_LEADS' }, resolve);
  });
}

async function init() {
  // Check if on LinkedIn (manual scraper panel only works there — Facebook automation
  // runs silently in the background via chrome.alarms, with no on-page panel to open)
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const isLinkedIn = tab?.url?.includes('linkedin.com');
  const isFacebook = tab?.url?.includes('facebook.com');
  const dot = document.getElementById('popStatusDot');
  const statusText = document.getElementById('popStatusText');

  if (isLinkedIn) {
    dot.className = 'p-status-dot on-linkedin';
    const pageType = tab.url.includes('/in/') ? 'Profile page' :
      tab.url.includes('/search/') ? 'Search results' :
      tab.url.includes('/company/') ? 'Company page' : 'LinkedIn page';
    statusText.textContent = `✓ On LinkedIn · ${pageType}`;
  } else if (isFacebook) {
    dot.className = 'p-status-dot on-linkedin';
    statusText.textContent = '✓ On Facebook · automation runs in the background, no manual panel here';
    document.getElementById('btnOpenSidebar').disabled = true;
    document.getElementById('btnOpenSidebar').style.opacity = '0.5';
  } else {
    dot.className = 'p-status-dot not-linkedin';
    statusText.textContent = 'Not on LinkedIn or Facebook';
    document.getElementById('btnOpenSidebar').disabled = true;
    document.getElementById('btnOpenSidebar').style.opacity = '0.5';
  }

  // Load stats
  const leads = await getLeads() || [];
  document.getElementById('statLeads').textContent = leads.length;
  document.getElementById('statEmails').textContent = leads.reduce((a, l) => a + (l.emails?.length || 0), 0);
  document.getElementById('statPhones').textContent = leads.reduce((a, l) => a + (l.phones?.length || 0), 0);

  // Recent leads preview
  const container = document.getElementById('recentLeads');
  if (leads.length === 0) {
    container.innerHTML = '<div class="p-empty">No leads saved yet.<br/>Open a LinkedIn profile and scrape!</div>';
  } else {
    container.innerHTML = '';
    leads.slice(0, 4).forEach(lead => {
      const initials = (lead.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
      const email = lead.emails?.[0] || lead.phones?.[0] || 'No contact info';
      const el = document.createElement('div');
      el.className = 'p-lead-mini';
      el.innerHTML = `
        <div class="p-lead-av">${initials}</div>
        <div style="flex:1;overflow:hidden">
          <div class="p-lead-name">${lead.name || 'Unknown'}</div>
          <div class="p-lead-email">${email}</div>
        </div>`;
      el.style.cursor = 'pointer';
      el.addEventListener('click', () => {
        if (lead.profileUrl) chrome.tabs.create({ url: lead.profileUrl });
      });
      container.appendChild(el);
    });
    if (leads.length > 4) {
      const more = document.createElement('div');
      more.style.cssText = 'text-align:center;font-size:10px;color:#475569;padding:6px 0';
      more.textContent = `+${leads.length - 4} more leads`;
      container.appendChild(more);
    }
  }
}

// Open sidebar panel
document.getElementById('btnOpenSidebar').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: 'TOGGLE_SIDEBAR' });
    window.close();
  }
});

// Open the automation Options page (chrome.runtime.openOptionsPage is the reliable,
// version-independent way to do this — no dependency on a right-click menu working).
document.getElementById('btnOpenOptions').addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});

// Export CSV
document.getElementById('btnExportCSV').addEventListener('click', async () => {
  const leads = await getLeads() || [];
  if (!leads.length) { alert('No leads to export!'); return; }

  const headers = ['Name','Title','Company','Location','Emails','Phones','LinkedIn URL','Scraped At'];
  const rows = leads.map(l => [
    l.name||'', l.title||'', l.company||'', l.location||'',
    (l.emails||[]).join(' | '), (l.phones||[]).join(' | '),
    l.profileUrl||'', l.scrapedAt ? new Date(l.scrapedAt).toLocaleString() : ''
  ]);
  const esc = v => `"${String(v).replace(/"/g,'""')}"`;
  const csv = [headers.map(esc).join(','), ...rows.map(r => r.map(esc).join(','))].join('\n');
  const blob = new Blob(['\uFEFF'+csv], {type:'text/csv;charset=utf-8;'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'leadlist_export.csv';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// Clear all
document.getElementById('btnClearAll').addEventListener('click', async () => {
  if (confirm('Delete all saved leads?')) {
    await new Promise(r => chrome.runtime.sendMessage({ type: 'CLEAR_LEADS' }, r));
    init();
  }
});

init();
