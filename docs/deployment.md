# Deployment

## Vercel and Blob

HydroSL uses Vercel for the static dashboard and GitHub Actions for the daily
source ingestion. The dashboard reads compact public JSON read models from a
Vercel Blob store. The local FastAPI service remains available for development
and future server-side features.

### One-time Vercel setup

1. Import `manjithahhu20/HydroSL` into Vercel.
2. Use the repository root as the project root. Do not set `apps/dashboard` as
   the root because the build configuration is at the repository root.
3. Use the `main` production branch.
4. Create a **public** Vercel Blob store for dashboard read models.
5. Connect the Blob store to the project if Vercel OIDC is available.
6. Add the Blob store's public base URL as the Vercel environment variable
   `HYDROSL_DATA_BASE` for Production and Preview. The value should point to
   the `hydrosl/` prefix, without a filename.

The Vercel build runs `npm run build` from `vercel.json` and publishes the
static files from `dist/`.

### GitHub Actions setup

Add a GitHub Actions secret named `BLOB_READ_WRITE_TOKEN`. It must be the
Vercel Blob read-write token, not a Vercel account/deployment token. The
workflow will:

1. Fetch all workbook sheets.
2. Normalize the warehouse.
3. Export compact dashboard read models.
4. Upload those read models to the `hydrosl/` Blob prefix.
5. Retain the full warehouse as a workflow artifact.

The publisher uses stable paths and `allowOverwrite`, so the dashboard URL does
not need to change after each daily update. Blob cache control is five minutes.

### Local static build

Generate read models locally:

```text
hydrosl export --warehouse data/warehouse --output apps/dashboard/data
```

Build the Vercel output:

```text
npm ci
npm run build
```

For local API development, `apps/dashboard/config.js` points to the local API.
The Vercel build generates `dist/config.js` from `HYDROSL_API_BASE` and
`HYDROSL_DATA_BASE` environment variables.

## Credential safety

Never commit Vercel or Blob tokens. If a token is pasted into chat, a terminal
log, an issue, or a source file, revoke it and create a replacement. Prefer
Vercel OIDC for code running on Vercel and use a narrowly scoped Blob token only
for the external GitHub Actions publisher.

## Data policy

Only the normalized read models should be public. Raw source snapshots and
parser details remain in workflow artifacts unless the source owner's
permission explicitly covers public redistribution.
