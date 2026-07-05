// Qualifay Agent - Pacing helpers
// Shared by the LinkedIn and Facebook content scripts. Keeps automated browsing from
// looking instant/robotic: randomized delays and a small amount of scrolling before any
// extraction runs.
window.QAgentPacing = (() => {
  function randomMs(minMs, maxMs) {
    return Math.floor(minMs + Math.random() * (maxMs - minMs));
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function humanDelay(minMs = 2500, maxMs = 6000) {
    await wait(randomMs(minMs, maxMs));
  }

  // Scroll the page a few times with pauses, like someone actually reading a feed.
  async function humanScroll(times = 4, minPause = 900, maxPause = 2200) {
    for (let i = 0; i < times; i++) {
      const distance = randomMs(400, 1200);
      window.scrollBy({ top: distance, behavior: 'smooth' });
      await wait(randomMs(minPause, maxPause));
    }
  }

  return { randomMs, wait, humanDelay, humanScroll };
})();
