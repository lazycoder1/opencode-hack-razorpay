import { chromium } from 'playwright';
import path from 'node:path';

const URL = process.argv[2] ?? 'http://127.0.0.1:3000/microsites/cred-8f35db';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(1500);
const out = path.resolve('docs/qa-microsite.png');
await page.screenshot({ path: out, fullPage: true });
console.log('saved', out);
await browser.close();
