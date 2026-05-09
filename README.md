# msh-geo-tracker

GEO Visibility Tracker — track how often your clients show up in ChatGPT, Perplexity, and Claude search results.

Live dashboard: https://allisonmarranca.github.io/msh-geo-tracker/

## How the pieces fit together

```
┌──────────────────┐    ⬆ Sync to GitHub    ┌──────────────────┐
│  Dashboard       │ ─────────────────────► │  clients.json    │  (source of truth)
│  (index.html)    │ ◄───────────────────── │  in this repo    │
│  GitHub Pages    │    ⬇ Pull on demand    └──────────────────┘
└──────────────────┘                                │
        ▲                                           ▼
        │                            ┌─────────────────────────────────┐
        │  ⬇ auto-loads on page open │  Scheduled GitHub Action        │
        │                            │  .github/workflows/scan.yml     │
        │      scan_results.json ◄── │  runs scripts/scan.py weekly    │
        │                            │  + on manual trigger            │
        └────────────────────────────└─────────────────────────────────┘
```

1. You add or edit clients in the dashboard. Changes save to your browser's localStorage immediately.
2. **⬆ Sync to GitHub** pushes `clients.json` to this repo via the GitHub API.
3. The scheduled GitHub Action reads `clients.json`, scans every client across the AI platforms, and commits an updated `scan_results.json`.
4. The dashboard auto-loads the latest `scan_results.json` on every page load.

## One-time setup

### 1. Add API keys as repo secrets

In GitHub, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name           | Where to get it                                                  |
|-----------------------|------------------------------------------------------------------|
| `OPENAI_API_KEY`      | https://platform.openai.com/api-keys                             |
| `PERPLEXITY_API_KEY`  | https://www.perplexity.ai/settings/api                           |
| `ANTHROPIC_API_KEY`   | https://console.anthropic.com/settings/keys                      |

The scanner skips any platform whose key isn't set, so you can start with one and add the others later.

### 2. Generate a GitHub personal access token (PAT)

For the dashboard's **⬆ Sync to GitHub** button, you need a token with `repo` scope.

- Go to https://github.com/settings/tokens?type=beta and click **Generate new token (fine-grained)**.
- Repository access: **Only select repositories → `msh-geo-tracker`**.
- Repository permissions: **Contents → Read and write**.
- Copy the token and paste it into **Settings → GitHub Sync → Personal Access Token** in the dashboard, then click **Save Token**.

The token lives only in your browser's localStorage. It is never sent anywhere except api.github.com.

### 3. Push your initial client list

In the dashboard:

1. Add or import clients (CSV or one-by-one).
2. Click **⬆ Sync to GitHub** in the Clients toolbar.
3. You should see ✓ Pushed N clients to GitHub.
4. The first scheduled run will pick them up.

## Running a scan

### Automatic (weekly)

The workflow runs every Monday at 09:00 UTC (~5am ET, see [.github/workflows/scan.yml](.github/workflows/scan.yml) to change the cadence). When it finishes, it commits the updated `scan_results.json` and the dashboard picks it up on its next page load.

### Manual

Go to the **Actions** tab → **GEO Scan** → **Run workflow**. You can optionally set `scan_limit` (e.g. `3`) to smoke-test on the first N clients only.

### Locally

```bash
pip install -r scripts/requirements.txt
export OPENAI_API_KEY=sk-...
export PERPLEXITY_API_KEY=pplx-...
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/scan.py
```

The script writes `scan_results.json` next to itself.

## Files

| File                         | What it is                                                              |
|------------------------------|-------------------------------------------------------------------------|
| `index.html`                 | The single-file dashboard, deployed via GitHub Pages.                   |
| `clients.json`               | Source of truth for your client list. Pushed by the dashboard.          |
| `scan_results.json`          | Latest scan output. Read by the dashboard on every load.                |
| `scripts/scan.py`            | Python scanner. Builds prompts, calls the AI APIs, scores responses.    |
| `scripts/requirements.txt`   | Python dependencies (just `requests`).                                  |
| `.github/workflows/scan.yml` | GitHub Actions workflow that runs the scanner on a schedule.            |

## Where things live in your browser

The dashboard uses `localStorage` for everything. Nothing is sent to any server unless you explicitly use a button that does so (Sync to GitHub, or any "Scan Now"-style button if those return).

| Key                     | What                                                |
|-------------------------|-----------------------------------------------------|
| `msh_clients_v1`        | Your client list                                    |
| `msh_evidence_v1`       | Evidence log of where mentions came from            |
| `msh_am_v1`             | Account manager name / role / email / phone        |
| `msh_gh_pat`            | GitHub personal access token (for sync)             |
| `msh_key_openai` etc.   | Per-platform API keys (only used if Scan Now runs)  |

To wipe everything, open the dashboard, hit DevTools → Application → Local Storage → clear, or use the Settings buttons.

## Adjusting the schedule

Edit the `cron:` line in `.github/workflows/scan.yml`. Some examples:

- `"0 9 * * 1"` — every Monday at 09:00 UTC (default)
- `"0 9 1 * *"` — first of every month at 09:00 UTC
- `"0 9 * * 1,4"` — Mondays and Thursdays
- `"0 */6 * * *"` — every 6 hours

GitHub's cron times are UTC. https://crontab.guru is good for verifying expressions.
