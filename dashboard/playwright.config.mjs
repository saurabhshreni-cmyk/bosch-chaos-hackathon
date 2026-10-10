import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./tests',testMatch:'browser.spec.mjs',workers:1,
  use:{baseURL:process.env.DASHBOARD_URL||'http://127.0.0.1:7010',channel:'msedge',headless:true},
});
