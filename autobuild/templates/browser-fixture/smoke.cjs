const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

async function main() {
  const output = process.env.AUTOBUILD_BROWSER_OUTPUT;
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.FIXTURE_CHROMIUM ? { executablePath: process.env.FIXTURE_CHROMIUM } : {}),
  });
  const context = await browser.newContext({ viewport: { width: 900, height: 600 } });
  await context.tracing.start({ screenshots: true, snapshots: true });
  const page = await context.newPage();
  let passed = false;
  try {
    await page.goto('http://127.0.0.1:38404', { waitUntil: 'networkidle' });
    assert.equal(await page.title(), 'Counter');
    assert.equal(await page.locator('#count').innerText(), '0');
    await page.getByRole('button', { name: 'Increment', exact: true }).click();
    assert.equal(await page.locator('#count').innerText(), '1', 'click must increment the real counter');
    passed = true;
  } finally {
    await page.screenshot({ path: path.join(output, 'counter.png'), fullPage: true });
    await context.tracing.stop({ path: path.join(output, 'trace.zip') });
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({ passed, url: page.url() }));
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
