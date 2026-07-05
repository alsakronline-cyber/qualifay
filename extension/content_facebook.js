// Qualifay Agent - Facebook content script entry point.
// The actual RUN_AGENT_TASK handling lives in utils/sync.js (shared with LinkedIn) so the
// automation logic isn't duplicated. This file just marks the page ready and gives a place
// to add a manual UI later if wanted — Facebook automation runs silently by design.
(function () {
  'use strict';
  console.debug('[Qualifay Agent] Facebook content script ready on', window.location.href);
})();
