# Putting the dashboard online (free)

[Version française](../DEPLOIEMENT.md)

The online dashboard is a **static site**: HTML, CSS and JavaScript reading
`dashboard/static/data/snapshot.json`, a copy of the results of a real pipeline run.
It needs no database and no Python server. As a result:

- hosting is free on several platforms;
- the page opens immediately (a static site does not "sleep", unlike a free web service);
- figures come from the last export, not live data. The full chain (PostgreSQL, Airflow, dbt)
  runs locally with Docker.

## Option 1: Render (recommended)

The `render.yaml` file at the root already describes the site.

1. Create a free account on https://render.com (sign in with GitHub).
2. **New** > **Blueprint**, then pick the `Retail-Inventory-or-and-Supply-Chain-Warehouse` repository.
3. Render reads `render.yaml` and creates the `retail-warehouse-dashboard` service (*Static Site*). Confirm.
4. After a minute the site is live at an address like
   `https://retail-warehouse-dashboard.onrender.com`.

Every `git push` to `main` redeploys the site automatically.

Without the Blueprint: **New** > **Static Site**, repository, empty *Build Command* (or `echo ok`),
*Publish Directory* `dashboard/static`.

## Option 2: GitHub Pages

1. On GitHub: **Settings** > **Pages**.
2. *Source*: **GitHub Actions**, pick the **Static HTML** template and set the published folder
   to `dashboard/static` (the `path:` line of the proposed workflow).
3. Address: `https://cheugs.github.io/Retail-Inventory-or-and-Supply-Chain-Warehouse/`.

## Option 3: Netlify or Vercel

Import the repository, leave the build command empty and set `dashboard/static` as the publish directory.

## Updating the figures on the site

```bash
python -m retail_pipeline.run all         # full pipeline, also writes the snapshot
git add dashboard/static/data/snapshot.json
git commit -m "Update dashboard snapshot"
git push
```

## What a recruiter sees

The sidebar shows the data source ("JSON snapshot" online, "live database" locally) and the
update date. The footer says that the data is synthetic.
