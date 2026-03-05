# Integration Guide — Adding CI Sherlock to Your App

This guide walks through adding CI Sherlock to a React (Vite) todo app with no existing tests or CI setup. By the end, every PR will automatically get an AI-generated analysis of what broke and why.

**What you'll set up:**
- Playwright end-to-end tests
- GitHub Actions CI workflow
- CI Sherlock analysis on every PR

---

## Prerequisites

- Node.js 18+
- Python 3.12+
- A React (Vite) app running locally
- A GitHub account

---

## Step 1 — Push your repo to GitHub

If your project isn't on GitHub yet:

```bash
git init
git add .
git commit -m "initial commit"
```

Create a new empty repo on GitHub (no README, no .gitignore), then push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/todo-app.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Install Playwright

In your project root:

```bash
npm init playwright@latest
```

When prompted:

| Prompt | Answer |
|---|---|
| Where to put tests? | `tests` |
| Add a GitHub Actions workflow? | **No** (CI Sherlock handles this) |
| Install Playwright browsers? | **Yes** |

This creates `playwright.config.ts` and a sample test file.

---

## Step 3 — Configure Playwright for JSON output

CI Sherlock reads the Playwright JSON report. Open `playwright.config.ts` and update it:

```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  retries: 2,                         // enables flaky detection in CI Sherlock
  reporter: [
    ['list'],
    ['json', { outputFile: 'playwright-report.json' }],   // required by CI Sherlock
  ],
  use: {
    baseURL: 'http://localhost:5173',  // your Vite dev server port
    trace: 'on-first-retry',
  },
});
```

---

## Step 4 — Write your first tests

Create `tests/todo.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('should add a todo item', async ({ page }) => {
  await page.getByPlaceholder('Add a task').fill('Buy milk');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Buy milk')).toBeVisible();
});

test('should mark a todo as complete', async ({ page }) => {
  await page.getByPlaceholder('Add a task').fill('Walk the dog');
  await page.keyboard.press('Enter');
  await page.getByText('Walk the dog').click();
  await expect(page.getByText('Walk the dog')).toHaveClass(/completed/);
});

test('should delete a todo item', async ({ page }) => {
  await page.getByPlaceholder('Add a task').fill('Clean desk');
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Clean desk')).not.toBeVisible();
});
```

> Adjust selectors to match your actual component structure.

Verify they pass locally before moving on:

```bash
npx playwright test
```

---

## Step 5 — Add the `wait-on` dependency

The CI workflow needs to wait for the Vite dev server to be ready before running tests:

```bash
npm install -D wait-on
```

---

## Step 6 — Add the CI workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium

      - name: Start dev server
        run: npm run dev &

      - name: Wait for server
        run: npx wait-on http://localhost:5173 --timeout 30000

      - name: Run Playwright tests
        run: npx playwright test
        continue-on-error: true   # allow sherlock job to always run

      - name: Upload Playwright report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: playwright-report.json
          retention-days: 7

  sherlock:
    needs: test
    runs-on: ubuntu-latest
    if: always()              # run even when tests fail
    permissions:
      pull-requests: write    # needed to post PR comments
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Download Playwright report
        uses: actions/download-artifact@v4
        with:
          name: playwright-report

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Run CI Sherlock
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pip install ci-sherlock --quiet
          ci-sherlock analyze
```

---

## Step 7 — Add your OpenAI API key to GitHub

`GITHUB_TOKEN` is provided automatically. You only need to add your OpenAI key.

1. Go to your repo on GitHub
2. Navigate to **Settings → Secrets and variables → Actions**
3. Click **New repository secret**
4. Set name to `OPENAI_API_KEY` and paste your key

Your key can be found at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

> **Note:** If you skip this step, CI Sherlock still runs — it posts the raw failure and correlation analysis without the AI root cause section.

---

## Step 8 — Open a PR to see it in action

Create a branch, make a change, and push:

```bash
git checkout -b feat/my-change
# make your changes
git add .
git commit -m "feat: my change"
git push origin feat/my-change
```

Open a pull request on GitHub. After the `test` job finishes, the `sherlock` job runs and posts a comment directly on the PR:

```
❌ 1 passed   2 failed   0 skipped — 12.3s total

### Root Cause
> The delete button was removed from the DOM. Two tests that rely
> on the Delete button can no longer find the element.

Confidence: 87%   Recommendation: restore the delete button or update selectors.

### Failure → Diff Correlation
| Test                        | Changed file  | Signal         | Score |
|-----------------------------|---------------|----------------|-------|
| should delete a todo item   | src/App.tsx   | same_directory | 0.6   |
```

---

## Optional — Run the dashboard locally

After a few CI runs, download the history DB artifact from GitHub Actions and view trends:

```bash
pip install ci-sherlock
ci-sherlock dashboard --db ./history.db
```

Opens a Streamlit UI with run history, flaky test leaderboard, slowest tests, and a release readiness score.

---

## Quick reference

| Task | Command |
|---|---|
| Run tests locally | `npx playwright test` |
| Run with interactive UI | `npx playwright test --ui` |
| Run sherlock locally | `ci-sherlock analyze --report playwright-report.json` |
| View dashboard | `ci-sherlock dashboard` |
| View Playwright report | `npx playwright show-report` |

---

## Troubleshooting

**`playwright-report.json` not found**
Make sure `reporter: [['json', { outputFile: 'playwright-report.json' }]]` is in your `playwright.config.ts` and the file path matches what's in the workflow upload step.

**Vite server not starting in CI**
Check that `npm run dev` starts on port 5173. If your port differs, update the `wait-on` URL and `baseURL` in `playwright.config.ts` to match.

**Sherlock posts no comment on push events**
CI Sherlock only posts PR comments when a PR number is detected. Push events to `main` still write to the SQLite DB for history — the comment is skipped because there's no PR to comment on.

**LLM section missing from comment**
`OPENAI_API_KEY` is not set or is invalid. The rest of the analysis (correlations, flaky detection, optimization signals) still runs and is posted.

---

## Optional — Slack notifications

Add `SHERLOCK_SLACK_WEBHOOK` to post a concise failure summary to a Slack channel.

1. Create an [Incoming Webhook](https://api.slack.com/messaging/webhooks) for your workspace.
2. Add the URL as a GitHub secret (`SHERLOCK_SLACK_WEBHOOK`).
3. Pass it to the workflow step:

```yaml
      - name: Run CI Sherlock
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          SHERLOCK_SLACK_WEBHOOK: ${{ secrets.SHERLOCK_SLACK_WEBHOOK }}
        run: |
          pip install ci-sherlock --quiet
          ci-sherlock analyze
```

CI Sherlock only posts to Slack when there are **failing tests** — green builds are silent.

---

## Optional — GitHub Actions step summary

CI Sherlock automatically writes the full analysis as a [Job Summary](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary) when the `GITHUB_STEP_SUMMARY` environment variable is set.

GitHub Actions sets this variable automatically on every runner — no configuration needed. The analysis appears in the **Summary** tab of your workflow run.
