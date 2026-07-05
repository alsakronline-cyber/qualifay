// LeadList - Contact Data Extractor
// Extracts emails, phones, and profile data from LinkedIn DOM

window.LeadListExtractor = (() => {

  const EMAIL_REGEX = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;
  const PHONE_REGEX = /(?:\+?\d{1,3}[\s\-.]?)?\(?\d{2,4}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4}(?:[\s\-.]?\d{1,4})?/g;
  const PHONE_MIN_DIGITS = 7;

  function extractEmails(text) {
    const found = text.match(EMAIL_REGEX) || [];
    return [...new Set(found.filter(e => !e.includes('linkedin') && !e.includes('example') && e.length < 80))];
  }

  function extractPhones(text) {
    const found = text.match(PHONE_REGEX) || [];
    return [...new Set(
      found
        .map(p => p.trim())
        .filter(p => {
          const digits = p.replace(/\D/g, '');
          return digits.length >= PHONE_MIN_DIGITS && digits.length <= 15;
        })
    )];
  }

  function getPageText() {
    return document.body ? document.body.innerText : '';
  }

  function getPageHTML() {
    return document.body ? document.body.innerHTML : '';
  }

  function getCleanText(selector, parent = document) {
    const el = parent.querySelector(selector);
    return el ? (el.innerText || el.textContent || '').trim() : '';
  }

  function extractProfileData() {
    const data = {
      name: '',
      title: '',
      company: '',
      location: '',
      profileUrl: window.location.href.split('?')[0],
      emails: [],
      phones: [],
      avatar: '',
      scrapedAt: Date.now()
    };

    // Name
    const nameSelectors = [
      'h1.text-heading-xlarge',
      'h1[class*="title"]',
      '.pv-top-card--list > li:first-child',
      'h1',
    ];
    for (const sel of nameSelectors) {
      const val = getCleanText(sel);
      if (val) {
        data.name = val;
        break;
      }
    }

    // Title / Headline
    const titleSelectors = [
      '.text-body-medium.break-words',
      '[data-generated-suggestion-target]',
      '.pv-top-card--experience-list-item',
      '.pv-top-card-section__headline',
      '.ph5 .text-body-medium',
    ];
    for (const sel of titleSelectors) {
      const val = getCleanText(sel);
      if (val) {
        data.title = val;
        break;
      }
    }

    // Company
    const companySelectors = [
      'button[aria-label*="Current company"]',
      '.pv-top-card--experience-list .pv-entity__secondary-title',
      '[aria-label*="company"]',
    ];
    for (const sel of companySelectors) {
      const val = getCleanText(sel);
      if (val) {
        data.company = val;
        break;
      }
    }
    // Fallback: look for experience section
    if (!data.company) {
      data.company = getCleanText('#experience ~ div .hoverable-link-text');
    }

    // Location
    const locSelectors = [
      '.pv-top-card--list.pv-top-card--list-bullet > li:nth-child(2)',
      '.text-body-small.inline.t-black--light.break-words',
      '[class*="location"]',
    ];
    for (const sel of locSelectors) {
      const val = getCleanText(sel);
      if (val) {
        data.location = val;
        break;
      }
    }

    // Avatar
    const avatarEl = document.querySelector('.pv-top-card-profile-picture__image, img.profile-photo-edit__preview, .presence-entity__image');
    if (avatarEl) data.avatar = avatarEl.src || '';

    // Fallback for name/title/company: LinkedIn's CSS classes rotate (auto-generated,
    // hashed), but the browser TAB TITLE stays a reliable, structurally-independent
    // signal — "Name - Role at Company | LinkedIn" (or a subset of that). If the
    // class-based selectors above came up empty (or even just the name), parse it from
    // document.title instead of giving up.
    if (!data.name || !data.title) {
      // Strip a leading unread-notification-count prefix, e.g. "(3) Name | LinkedIn".
      const head = (document.title || '')
        .replace(/^\(\d+\)\s*/, '')
        .split(/\s*[|]\s*LinkedIn\b/i)[0]
        .trim();
      const parts = head.split(/\s+[-–]\s+/).map((s) => s.trim()).filter(Boolean);
      if (!data.name && parts[0]) data.name = parts[0];
      if (!data.title && parts[1]) {
        const atMatch = parts[1].match(/^(.*?)\s+at\s+(.+)$/i);
        data.title = atMatch ? atMatch[1].trim() : parts[1];
        if (!data.company && atMatch) data.company = atMatch[2].trim();
      }
      if (!data.company && parts[2]) data.company = parts[2];
    }

    // Extract from page text
    const pageText = getPageText();
    data.emails = extractEmails(pageText);
    data.phones = extractPhones(pageText);

    return data;
  }

  function extractSearchResults() {
    // LinkedIn's search-result markup uses auto-generated, hashed utility classes that
    // rotate on their own schedule (e.g. "fee11784 _20dea5d9 _50ed7e79") — matching those
    // exactly is a losing game. The one thing that stays stable is the profile URL itself
    // (always contains "/in/"), so we anchor on that and walk up to find each card, then
    // parse the card's plain text structurally instead of via CSS classes.
    const results = [];
    const seenHrefs = new Set();
    const anchors = document.querySelectorAll('a[href*="/in/"]');

    anchors.forEach((a) => {
      const href = (a.href || '').split('?')[0];
      if (!href.includes('/in/') || seenHrefs.has(href)) return;
      const name = (a.innerText || '').trim();
      // Skip anchors that wrap a whole card (long text) or are empty (e.g. avatar-only links).
      if (!name || name.length > 60) return;
      seenHrefs.add(href);

      // Walk up until the container holds meaningfully more text than just the name —
      // that's the card boundary (title/company/location/mutual-connection lines live there).
      let card = a;
      for (let i = 0; i < 6 && card.parentElement; i++) {
        card = card.parentElement;
        if ((card.innerText || '').length > name.length + 15) break;
      }

      const lines = (card.innerText || '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);

      // First line is the name, possibly with a trailing "· 1st/2nd/3rd+" connection badge.
      const cleanName = (lines[0] || name).replace(/\s*[·•]\s*(1st|2nd|3rd\+?)\s*$/i, '').trim();

      // Skip "X is a mutual connection" mention links — these also point to a /in/ profile
      // (LinkedIn hyperlinks the mentioned person's name) but aren't a search result at all.
      if (/mutual connection/i.test(cleanName) || /mutual connection/i.test(lines[1] || '')) return;

      // On verified/badge accounts the "· 2nd" connection-degree marker sometimes lands on
      // its own line instead of trailing the name, shifting the real title down an index —
      // drop any line after the first that's ONLY that marker before picking the subtitle.
      const DEGREE_ONLY = /^[·•]?\s*(1st|2nd|3rd\+?)\s*$/i;
      const meaningfulLines = lines.filter((l, i) => i === 0 || !DEGREE_ONLY.test(l));
      const subtitleLine = meaningfulLines[1] || '';
      const atMatch = subtitleLine.match(/^(.*?)\s+at\s+(.+)$/i);
      const title = atMatch ? atMatch[1].trim() : subtitleLine;
      const company = atMatch ? atMatch[2].trim() : '';

      const cardText = card.innerText || '';
      results.push({
        name: cleanName || name,
        title,
        company,
        profileUrl: href,
        emails: extractEmails(cardText),
        phones: extractPhones(cardText),
        scrapedAt: Date.now(),
      });
    });

    return results;
  }

  async function openContactModal() {
    return new Promise((resolve) => {
      const btn = document.querySelector(
        'a[href*="overlay/contact-info"], button[aria-label*="contact info"], a[data-control-name*="contact_see_more"]'
      );
      if (!btn) return resolve(null);

      btn.click();
      let attempts = 0;
      const interval = setInterval(() => {
        attempts++;
        const modal = document.querySelector('.pv-contact-info__contact-type, .artdeco-modal__content, [data-test-modal]');
        if (modal) {
          clearInterval(interval);
          const text = modal.innerText || '';
          const emails = extractEmails(text);
          const phones = extractPhones(text);
          // close modal
          const closeBtn = document.querySelector('.artdeco-modal__dismiss, button[aria-label="Dismiss"]');
          if (closeBtn) closeBtn.click();
          resolve({ emails, phones });
        }
        if (attempts > 20) {
          clearInterval(interval);
          resolve(null);
        }
      }, 300);
    });
  }

  function getPageType() {
    const url = window.location.href;
    if (url.includes('/in/') && !url.includes('/search/')) return 'profile';
    if (url.includes('/search/results/people')) return 'search_people';
    if (url.includes('/search/results/')) return 'search';
    if (url.includes('/company/')) return 'company';
    if (url.includes('/sales/')) return 'sales';
    return 'other';
  }

  return { extractProfileData, extractSearchResults, openContactModal, extractEmails, extractPhones, getPageType, getPageText };
})();
