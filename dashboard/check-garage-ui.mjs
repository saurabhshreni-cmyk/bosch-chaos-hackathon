import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '@playwright/test';

const baseURL = 'http://127.0.0.1:7005';
const output = new URL('./runtime/garage-ui/', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    for (const route of ['/', '/Home/About', '/CustomerManagement', '/VehicleManagement',
      '/WorkshopManagement', '/CustomerManagement/New', '/VehicleManagement/New',
      '/WorkshopManagement/New']) {
      const response = await page.goto(baseURL + route);
      assert.equal(response.status(), 200, route);
      await page.locator('#PageTitle').waitFor();
      const styles = await page.evaluate(() => ({
        background: getComputedStyle(document.body).backgroundColor,
        navigation: getComputedStyle(document.querySelector('nav')).backgroundColor,
        overflow: document.documentElement.scrollWidth > innerWidth,
        offline: document.body.innerText.includes('temporarily unavailable'),
      }));
      assert.equal(styles.background, 'rgb(243, 245, 246)', route);
      assert.equal(styles.navigation, 'rgb(32, 36, 40)', route);
      assert.equal(styles.overflow, false, `${route}: horizontal overflow at ${viewport.width}px`);
      assert.equal(styles.offline, false, `${route}: unavailable module`);
      if (route.endsWith('/New')) {
        const submit = page.locator('#SubmitButton');
        assert.equal(await submit.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(230, 191, 101)');
        await page.locator('.form-control').first().focus();
        await expect(page.locator('.form-control').first()).toHaveCSS('border-top-color', 'rgb(17, 107, 124)');
      }
      await page.screenshot({ path: fileURLToPath(new URL(`${viewport.width}-${route.replaceAll('/', '-') || 'home'}.png`, output)), fullPage: true });
    }
    if (viewport.width < 768) {
      await page.locator('.navbar-toggle').click();
      await page.locator('[id="MainMenu.CustomerManagement"]').click();
      await page.waitForURL('**/CustomerManagement');
    } else {
      await page.locator('[id="MainMenu.CustomerManagement"]').click();
      await page.waitForURL('**/CustomerManagement');
    }
    await page.locator('#RegisterCustomerButton').click();
    await page.waitForURL('**/CustomerManagement/New');
    await page.locator('#CancelButton').click();
    await page.waitForURL('**/CustomerManagement');
    assert.deepEqual(errors, [], 'Browser JavaScript errors');
    await page.close();
    console.log(`PASS: garage pages, forms, navigation and colors at ${viewport.width}px`);
  }
} finally {
  await browser.close();
}
