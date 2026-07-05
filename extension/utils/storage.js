// LeadList - Storage Utility
window.LeadListStorage = (() => {
  function sendMessageSafe(message, resolve) {
    if (!chrome.runtime || !chrome.runtime.id) {
      console.warn('[LeadList] Extension context invalidated. Please refresh the page.');
      return resolve(null);
    }
    try {
      chrome.runtime.sendMessage(message, (res) => {
        if (chrome.runtime.lastError) {
          // Context invalidation also manifests as an error in lastError
          console.warn('[LeadList] Runtime message failed:', chrome.runtime.lastError.message);
          resolve(null);
        } else {
          resolve(res);
        }
      });
    } catch (e) {
      console.warn('[LeadList] Error sending message:', e.message);
      resolve(null);
    }
  }

  return {
    async saveLead(lead) {
      return new Promise(resolve => sendMessageSafe({ type: 'SAVE_LEAD', lead }, resolve));
    },
    async getLeads() {
      return new Promise(resolve => sendMessageSafe({ type: 'GET_LEADS' }, resolve));
    },
    async deleteLead(id) {
      return new Promise(resolve => sendMessageSafe({ type: 'DELETE_LEAD', id }, resolve));
    },
    async clearLeads() {
      return new Promise(resolve => sendMessageSafe({ type: 'CLEAR_LEADS' }, resolve));
    },
    async getSettings() {
      return new Promise(resolve => sendMessageSafe({ type: 'GET_SETTINGS' }, resolve));
    },
    async saveSettings(settings) {
      return new Promise(resolve => sendMessageSafe({ type: 'SAVE_SETTINGS', settings }, resolve));
    }
  };
})();
