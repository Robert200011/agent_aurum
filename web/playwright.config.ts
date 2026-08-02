import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 300_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.AURUM_E2E_BASE_URL ?? 'http://127.0.0.1:4173',
    channel: process.env.AURUM_E2E_BROWSER_CHANNEL ?? 'msedge',
    trace: 'retain-on-failure',
    ...devices['Desktop Edge'],
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
