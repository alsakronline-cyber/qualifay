// Qualifay Agent - Sync
// Runs in both the LinkedIn and Facebook content-script contexts. Listens for the
// background worker's RUN_AGENT_TASK message (sent only to the exact tab it opened for
// that task), waits a human-like delay, runs the platform's extractor, and reports the
// results back. This is the only entry point for the automated (no-click) path — the
// LinkedIn sidebar's manual "scrape" button is untouched and still works independently.

(function () {
  'use strict';

  function platformOf() {
    const host = window.location.hostname;
    if (host.includes('linkedin.com')) return 'linkedin';
    if (host.includes('facebook.com')) return 'facebook';
    return null;
  }

  async function runLinkedInTask(task) {
    if (task.type === 'linkedin_profile_visit') {
      return runLinkedInProfileVisit();
    }
    await window.QAgentPacing.humanDelay(2000, 4500);
    await window.QAgentPacing.humanScroll(3);
    const results = window.LeadListExtractor
      ? window.LeadListExtractor.extractSearchResults()
      : [];
    return results.map((r) => ({
      name: r.name || null,
      title: r.title || null,
      company: r.company || null,
      phone: (r.phones && r.phones[0]) || null,
      email: (r.emails && r.emails[0]) || null,
      url: r.profileUrl || null,
    }));
  }

  // Visits a single profile page and opens the "Contact info" modal — the only place
  // LinkedIn actually shows an email/phone. Mirrors content.js's manual SCRAPE_CURRENT
  // profile flow so both paths behave identically.
  // Chrome throttles JS timers in background (unfocused) tabs — a fixed 2.5-5s delay that
  // works fine in a foreground tab isn't reliable there, because the LinkedIn SPA's own
  // hydration is throttled the same way and may not have rendered real content yet. Poll
  // for a real profile title (document.title moves past the generic "LinkedIn" default)
  // instead of guessing a fixed wait, with a generous cap for slow background loads.
  async function waitForProfileReady(maxMs = 15000, stepMs = 500) {
    const start = Date.now();
    while (Date.now() - start < maxMs) {
      const title = (document.title || '').trim();
      if (title && !/^\(?\d*\)?\s*linkedin$/i.test(title) && title.length > 'LinkedIn'.length) {
        return;
      }
      await window.QAgentPacing.wait(stepMs);
    }
  }

  async function runLinkedInProfileVisit() {
    if (!window.LeadListExtractor) return [];
    await waitForProfileReady();
    await window.QAgentPacing.humanDelay(1000, 2000);
    const result = window.LeadListExtractor.extractProfileData();
    try {
      const modalData = await window.LeadListExtractor.openContactModal();
      if (modalData) {
        result.emails = [...new Set([...(result.emails || []), ...(modalData.emails || [])])];
        result.phones = [...new Set([...(result.phones || []), ...(modalData.phones || [])])];
      }
    } catch (e) {
      console.warn('[Qualifay Agent] contact modal failed:', e);
    }
    if (!result.name) return [];
    return [{
      name: result.name,
      title: result.title || null,
      company: result.company || null,
      phone: (result.phones && result.phones[0]) || null,
      email: (result.emails && result.emails[0]) || null,
      url: result.profileUrl || null,
    }];
  }

  async function runFacebookTask(task) {
    await window.QAgentPacing.humanDelay(3000, 6000);
    // Groups/pages lazy-load on scroll — a shallow scroll only samples the top of the
    // feed (often pinned/admin posts, not real activity). Scroll much deeper so a single
    // run actually reaches where genuine buyer-intent posts are likely to live.
    await window.QAgentPacing.humanScroll(18, 1000, 2000);
    if (!window.QAgentFacebookExtractor) return [];
    // extractBuyerIntentPosts is async now — it also expands and reads comment threads,
    // since buy/sell groups often carry buyer intent as a comment on someone else's
    // listing ("بكام السعر؟") rather than as a brand-new post.
    return window.QAgentFacebookExtractor.extractBuyerIntentPosts();
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type !== 'RUN_AGENT_TASK') return;
    const task = message.task;
    const platform = platformOf();
    if (!platform || task.platform !== platform) return;

    (async () => {
      let items = [];
      try {
        items = platform === 'linkedin' ? await runLinkedInTask(task) : await runFacebookTask(task);
      } catch (e) {
        console.warn('[Qualifay Agent] extraction failed:', e);
      }
      chrome.runtime.sendMessage({
        type: 'AGENT_SCRAPE_RESULT',
        taskId: task.id,
        platform: task.platform,
        items,
      });
    })();

    sendResponse({ ok: true });
    return true;
  });
})();
