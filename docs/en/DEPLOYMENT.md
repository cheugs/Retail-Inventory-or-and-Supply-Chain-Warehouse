# Online demo: data updated every day

[Version française](../DEPLOIEMENT.md)

## How it works

```mermaid
flowchart LR
    GA["GitHub Actions<br/>every day 05:30 UTC"] -->|"simulates yesterday<br/>ingest, dbt build, reconciliation"| N[("Neon<br/>free PostgreSQL")]
    GA -->|"today's snapshot.json"| GP["GitHub Pages<br/>static dashboard"]
    N --> R["Render (optional)<br/>live dashboard"]
```

- **The online company** is a smaller version of the local demo (4 stores, 120 products, 10 suppliers)
  that "opened" on 1 September 2026. Every morning the `.github/workflows/daily-load.yml` workflow
  simulates yesterday and loads it into the warehouse hosted on **Neon**, with exactly the same code as
  the local version (`python -m retail_pipeline.run live-update`): ingestion, `dbt build` with its 48
  tests, reconciliation. The history grows by one day every day.
- **GitHub Pages** (https://cheugs.github.io/Retail-Inventory-or-and-Supply-Chain-Warehouse/) then gets
  the day's figures. The page opens at once and its "Updated" date changes every day.
- **Render** (optional) serves the same dashboard reading Neon live. The free plan sleeps: the first
  load can take about a minute.

The simulation always restarts from 1 September with the same random seed and planning horizon: days
already loaded are generated identically, and only the new day is loaded
(test `test_one_more_day_does_not_change_the_past`).

## One-time setup

### 1. Create the Neon database (free, about 3 minutes)

1. Create an account on https://neon.tech (sign in with GitHub works).
2. **Create project**: name `retail-warehouse`, PostgreSQL 16 or newer, Europe region (Frankfurt).
3. On the project page, **Connect** button: copy the connection string. It looks like
   `postgresql://user:password@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`.

Never paste this string in the code or in a file tracked by Git: it contains the password.

### 2. Give the string to GitHub (secret)

1. On GitHub, in the repository: **Settings** > **Secrets and variables** > **Actions** > **New repository secret**.
2. Name: `NEON_DATABASE_URL`, value: the copied string. **Add secret**.
3. **Actions** tab > **Daily load (live demo)** > **Run workflow**. The first run loads the whole history
   since 1 September (about 5 to 10 minutes) and publishes the dashboard. After that it runs on its own
   every morning.

### 3. (Optional) Live dashboard on Render

1. Free account on https://render.com (sign in with GitHub).
2. **New** > **Blueprint**, pick the repository. Render reads `render.yaml` (service
   `retail-warehouse-live`, built from the root `Dockerfile`).
3. Render asks for the `DATABASE_URL` value: paste the same Neon string. Confirm.
4. After a few minutes the site is live. This project's address: https://retail-warehouse-live-8lnt.onrender.com
   The sidebar shows "live database".

If the database does not answer, the server shows the last saved snapshot instead of an error.

## Free plan limits

- Neon: 0.5 GB of storage. The online company uses about 1 MB per day, so about 370 MB after one year.
  To start over: empty the Neon database and change `SIM_START_DATE` in `daily-load.yml`.
- Neon pauses when idle: the first query of the morning wakes it up (a few seconds).
- Render sleeps after 15 minutes without visits.
- GitHub scheduled workflows can start a bit late, and GitHub disables them if the repository has no
  activity for 60 days (one click on **Enable workflow** restarts them).

## Updating the reference demo (90 days)

The README results (section 9) come from the local 90-day demo dataset. The repository file
`dashboard/static/data/snapshot.json` is a copy of it; it is the fallback until the daily workflow has run.

```bash
python -m retail_pipeline.run all
git add dashboard/static/data/snapshot.json
git commit -m "Update reference snapshot"
git push
```
