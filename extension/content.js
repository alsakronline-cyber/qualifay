// LeadList - Content Script
(function () {
  'use strict';
  let sidebarFrame = null;
  let sidebarVisible = false;
  let toggleBtn = null;

  function createToggleButton() {
    if (document.getElementById('ll-toggle-btn')) return;
    toggleBtn = document.createElement('div');
    toggleBtn.id = 'll-toggle-btn';
    toggleBtn.title = 'Open LeadList';
    toggleBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="2" y="14" width="5" height="8" rx="1.5" fill="white"/><rect x="9.5" y="8" width="5" height="14" rx="1.5" fill="white"/><rect x="17" y="2" width="5" height="20" rx="1.5" fill="white"/><circle cx="4.5" cy="11" r="1.8" fill="white"/><circle cx="19.5" cy="18" r="1.8" fill="white"/></svg><span>LeadList</span>`;
    toggleBtn.addEventListener('click', toggleSidebar);
    document.body.appendChild(toggleBtn);
  }

  function createSidebar() {
    if (document.getElementById('ll-sidebar-frame')) return;
    sidebarFrame = document.createElement('iframe');
    sidebarFrame.id = 'll-sidebar-frame';
    sidebarFrame.src = chrome.runtime.getURL('sidebar/sidebar.html');
    sidebarFrame.setAttribute('allow', 'clipboard-write');
    sidebarFrame.style.cssText = 'position:fixed;top:0;right:-420px;width:420px;height:100vh;border:none;z-index:2147483647;transition:right 0.35s cubic-bezier(0.4,0,0.2,1);box-shadow:-8px 0 40px rgba(0,0,0,0.18);';
    document.body.appendChild(sidebarFrame);
  }

  function toggleSidebar() {
    sidebarVisible = !sidebarVisible;
    if (sidebarFrame) sidebarFrame.style.right = sidebarVisible ? '0px' : '-420px';
    if (toggleBtn) toggleBtn.classList.toggle('ll-active', sidebarVisible);
    document.body.style.marginRight = sidebarVisible ? '420px' : '';
    document.body.style.transition = 'margin-right 0.35s cubic-bezier(0.4,0,0.2,1)';
  }

  function postToSidebar(action, payload) {
    if (sidebarFrame && sidebarFrame.contentWindow) {
      sidebarFrame.contentWindow.postMessage({ source: 'leadlist-content', action, payload }, '*');
    }
  }

  window.addEventListener('message', async (event) => {
    if (event.data?.source !== 'leadlist-sidebar') return;
    const { action, payload } = event.data;

    if (action === 'SCRAPE_CURRENT') {
      const pageType = window.LeadListExtractor.getPageType();
      if (pageType === 'profile') {
        const result = window.LeadListExtractor.extractProfileData();
        try {
          const modalData = await window.LeadListExtractor.openContactModal();
          if (modalData) {
            result.emails = [...new Set([...result.emails, ...modalData.emails])];
            result.phones = [...new Set([...result.phones, ...modalData.phones])];
          }
        } catch(e) {}
        if (result.name) await window.LeadListStorage.saveLead(result);
        postToSidebar('SCRAPE_RESULT', { type: 'profile', lead: result });
      } else if (pageType.includes('search')) {
        const results = window.LeadListExtractor.extractSearchResults();
        for (const r of results) if (r.name) await window.LeadListStorage.saveLead(r);
        postToSidebar('SCRAPE_RESULT', { type: 'search', leads: results });
      } else {
        postToSidebar('SCRAPE_RESULT', { type: 'other', lead: null });
      }
    }
    if (action === 'GET_LEADS') {
      const leads = await window.LeadListStorage.getLeads();
      postToSidebar('LEADS_DATA', { leads });
    }
    if (action === 'DELETE_LEAD') {
      await window.LeadListStorage.deleteLead(payload.id);
      const leads = await window.LeadListStorage.getLeads();
      postToSidebar('LEADS_DATA', { leads });
    }
    if (action === 'CLEAR_LEADS') {
      await window.LeadListStorage.clearLeads();
      postToSidebar('LEADS_DATA', { leads: [] });
    }
    if (action === 'CLOSE_SIDEBAR') { if (sidebarVisible) toggleSidebar(); }
    if (action === 'EXPORT_CSV') {
      const leads = await window.LeadListStorage.getLeads();
      window.LeadListExporter.downloadCSV(leads);
    }
    if (action === 'EXPORT_JSON') {
      const leads = await window.LeadListStorage.getLeads();
      window.LeadListExporter.downloadJSON(leads);
    }
  });

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'TOGGLE_SIDEBAR') toggleSidebar();
  });

  let lastUrl = location.href;
  new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      setTimeout(() => postToSidebar('PAGE_CHANGED', { url: lastUrl, pageType: window.LeadListExtractor.getPageType() }), 1500);
    }
  }).observe(document.body, { subtree: true, childList: true });

  function init() {
    createToggleButton();
    createSidebar();
    setTimeout(() => postToSidebar('PAGE_CHANGED', { url: location.href, pageType: window.LeadListExtractor.getPageType() }), 2000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
