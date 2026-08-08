const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const context = browser.contexts()[0];
  const page = context.pages()[0];
  await page.screenshot({ path: 'C:/Users/matianyuan/.claude/hermes-screenshot.png', fullPage: false });
  await browser.close();
  console.log('Screenshot saved');
})();
