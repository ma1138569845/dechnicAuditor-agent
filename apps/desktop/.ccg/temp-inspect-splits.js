const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const context = browser.contexts()[0];
  const page = context.pages()[0];
  const result = await page.evaluate(() => {
    const splits = Array.from(document.querySelectorAll('[data-tree-split]'));
    return splits.map(s => ({
      id: s.getAttribute('data-tree-split'),
      rect: s.getBoundingClientRect(),
      children: Array.from(s.children).map(c => ({
        tag: c.tagName,
        class: c.className?.slice(0, 80),
        dataset: Object.keys(c.dataset),
        rect: c.getBoundingClientRect()
      }))
    }));
  });
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})();
