// Qualifay Agent - Facebook Extractor
// Reads posts from a group/page feed and keeps only ones that look like buyer intent
// (mirrors backend/scrapers/intent.py so the client-side pre-filter and the server-side
// AI confirmation agree on what counts as a candidate). The AI still re-checks every
// candidate server-side before a lead is created — this filter only avoids sending
// obvious non-matches over the wire.

window.QAgentFacebookExtractor = (() => {
  const TASHKEEL = /[ً-ْٰـ]/g;

  function normalizeAr(text) {
    if (!text) return '';
    let t = text.replace(TASHKEEL, '');
    for (const a of ['أ', 'إ', 'آ']) t = t.split(a).join('ا');
    t = t.split('ى').join('ي').split('ئ').join('ي').split('ؤ').join('و');
    return t.toLowerCase();
  }

  const BUYER_RAW = [
    'محتاج', 'محتاجه', 'محتاجين', 'عايز', 'عايزه', 'عاوز', 'عاوزه', 'عايزين',
    'اريد', 'اريده', 'نفسي اشتري', 'حابب اشتري', 'حابه اشتري', 'عايز اشتري', 'عاوز اشتري',
    'مطلوب', 'مطلوبه', 'للشراء',
    'بدور علي', 'بدور على', 'بدوّر', 'بدور', 'فين الاقي', 'فين اجيب', 'فين ممكن',
    'حد يعرف', 'حد عنده', 'حد يبيع', 'مين عنده', 'مين يعرف', 'ممكن حد', 'حد يرشح',
    'ينصحني', 'توصيه', 'ترشيح', 'استفسار',
    'بكام', 'السعر كام', 'عايز اعرف السعر', 'عرض سعر', 'سعر الـ', 'بيتباع بكام',
    'looking for', 'need a', 'need to buy', 'want to buy', 'anyone selling',
    'where can i find', 'where to buy', 'how much', 'price for', 'who sells',
    'recommend', 'searching for', 'interested in buying', 'any supplier',
  ];
  const BUYER_KEYWORDS = BUYER_RAW.map(normalizeAr);

  const SELLER_RAW = [
    'للبيع', 'للايجار', 'متاح للبيع', 'خصم', 'عرض خاص', 'اطلب الان', 'تواصل معنا',
    'للتواصل والطلب', 'اتصل بنا', 'we sell', 'for sale', 'shop now', 'order now', 'dm to order',
  ];
  const SELLER_KEYWORDS = SELLER_RAW.map(normalizeAr);

  const STRONG_BUYER = ['محتاج', 'عايز اشتري', 'عاوز اشتري', 'مطلوب',
    'want to buy', 'looking for', 'need to buy'];

  const PHONE_RE = /(?:\+?20|0020)?0?1[0125]\d{8}/;

  function detectBuyerIntent(text) {
    const n = normalizeAr(text);
    if (!BUYER_KEYWORDS.some((k) => n.includes(k))) return false;
    const sellerHits = SELLER_KEYWORDS.filter((k) => n.includes(k)).length;
    const strongBuyer = STRONG_BUYER.map(normalizeAr).some((k) => n.includes(k));
    if (sellerHits >= 2 && !strongBuyer) return false;
    return true;
  }

  function extractPhone(text) {
    if (!text) return null;
    const compact = text.replace(/[\s\-()]/g, '');
    const m = compact.match(PHONE_RE);
    return m ? m[0] : null;
  }

  function extractPosts() {
    const out = [];
    const articles = document.querySelectorAll('[role="article"]');
    articles.forEach((a) => {
      const text = (a.innerText || '').trim();
      if (!text) return;
      const link = a.querySelector(
        'a[href*="/permalink/"], a[href*="/posts/"], a[href*="story_fbid"]'
      );
      const url = link ? link.href : '';
      const authorEl = a.querySelector('h2 a, h3 a, strong a, span strong');
      const author = authorEl ? (authorEl.innerText || '').trim() : '';
      out.push({ text, url, author });
    });
    return out;
  }

  // In buy/sell equipment groups, many posts are photo-only listings with little or no
  // caption — the actual "بكام السعر؟ / how much?" buyer language usually shows up as a
  // COMMENT under someone else's sale post, not as its own new post. Comments are
  // distinguished from posts by having a "Reply" action (posts have "Comment" instead);
  // their container sits ~5 DOM levels above the Reply button in current Facebook markup.
  const EXPAND_LINK_RE = /view\s+\d+\s+more\s+comments?|^\d+\s+more\s+comments?$|عرض.*تعليق|مزيد من التعليقات/i;

  async function expandHiddenComments(maxClicks = 6, waitMs = 900) {
    let clicked = 0;
    for (let i = 0; i < maxClicks; i++) {
      const clickable = [...document.querySelectorAll('[role="button"], a')].find(
        (el) => el.children.length === 0 && EXPAND_LINK_RE.test((el.innerText || '').trim())
      );
      if (!clickable) break;
      clickable.click();
      clicked++;
      await new Promise((r) => setTimeout(r, waitMs));
    }
    return clicked;
  }

  function extractComments() {
    const out = [];
    const seenNodes = new Set();
    const replyButtons = [...document.querySelectorAll('[role="button"], div')].filter(
      (el) => el.children.length === 0 && (el.innerText || '').trim() === 'Reply'
    );
    replyButtons.forEach((btn) => {
      let node = btn;
      for (let i = 0; i < 5 && node.parentElement; i++) node = node.parentElement;
      if (seenNodes.has(node)) return;
      seenNodes.add(node);

      let text = (node.innerText || '').trim();
      // Strip the trailing action row ("5h\nLike\nReply\nShare" or similar).
      text = text.replace(/\n?[\d]+\s*[hdwm]?\n?Like\nReply\nShare\s*$/i, '');
      text = text.replace(/\nLike\nReply\nShare\s*$/i, '');
      const lines = text.split('\n').map((s) => s.trim()).filter(Boolean);
      if (!lines.length) return;
      const author = lines[0];
      const body = lines.filter((l, i) => i > 0 && l.toLowerCase() !== 'author').join(' ').trim();
      if (!body) return;
      out.push({ author, text: body });
    });
    return out;
  }

  async function extractBuyerIntentPosts() {
    const postMatches = extractPosts()
      .filter((p) => detectBuyerIntent(p.text))
      .map((p) => ({
        name: p.author || null,
        phone: extractPhone(p.text),
        url: p.url || null,
        text: p.text.slice(0, 1500),
        source: 'post',
      }));

    // Cap comment-expansion effort — this is extra automation work on top of the post
    // scan, so keep it bounded rather than clicking every "more comments" link on the page.
    await expandHiddenComments(6, 900);
    const commentMatches = extractComments()
      .filter((c) => detectBuyerIntent(c.text))
      .map((c) => ({
        name: c.author || null,
        phone: extractPhone(c.text),
        url: window.location.href.split('?')[0],
        text: c.text.slice(0, 1500),
        source: 'comment',
      }));

    return [...postMatches, ...commentMatches];
  }

  function getPageType() {
    const url = window.location.href;
    if (url.includes('/groups/')) return 'group';
    return 'other';
  }

  return { detectBuyerIntent, extractPhone, extractPosts, extractBuyerIntentPosts, getPageType, normalizeAr };
})();
