import { defineConfig } from '@playwright/test'

// AI Plan §12 task 10: one browser-level happy-path test derived from the
// `legal_two_team` golden case (golden/cases.yaml). PROVIDER=mock drives
// the *backend's* verdict provider (deterministic CBA math, no bball-GM
// network dependency) -- interpret/respond still make real Anthropic
// calls, same as the golden-case eval itself, since NLU is the thing
// under test and there is no fake-LLM path wired into the real server.
// Requires ANTHROPIC_API_KEY in the environment (see .env / README).
export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  fullyParallel: false, // one shared pair of dev servers; avoid session_id collisions across parallel workers
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      // Windows cmd.exe (the shell node spawns this through) doesn't reliably
      // resolve a forward-slash relative path as the executable -- backslash
      // it explicitly rather than relying on shell path normalization.
      command: String.raw`.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`,
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: { PROVIDER: 'mock' },
    },
    {
      command: 'npm run dev',
      cwd: './frontend',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
})
