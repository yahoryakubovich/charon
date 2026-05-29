# Web Dashboard

## Starting the dashboard

```bash
charon web
# → http://127.0.0.1:8765
```

You can bind to a different address or port:

```bash
charon web --host 0.0.0.0 --port 9000
```

---

## Layout

### Instance Status

Two cards at the top show live connectivity and stats for **SRC** and **DST**:

- Host URL
- Database name
- Table count
- Total row count (formatted as K/M/B)
- Total size (formatted as B/KB/MB/GB/TB)
- Ping indicator (green = online, red = offline)

Click **Refresh** to re-check connectivity.

### Tables comparison

A table grid shows all source tables alongside their destination counterparts:

| Column | Description |
|---|---|
| (checkbox) | Select for targeted copy |
| Table | Table name |
| Engine | ClickHouse engine |
| Src rows | Row count on source |
| Dst rows | Row count on destination (— if missing) |
| Diff | `src_rows − dst_rows` (coloured: yellow=surplus, red=negative) |
| Status | `ok` / `mismatch` / `missing` badge |

Actions:
- **Copy All** — starts a copy job for the entire database
- **Copy Selected** — starts a copy job for each checked table
- **Refresh** — reloads the diff

### Active Job panel

Appears when a copy job is running or has just finished:

- Job ID, status badge
- Scrollable log panel fed by SSE (auto-scrolls to bottom)
- **Dismiss** button

### Job History

Collapsible accordion showing the last 20 jobs. Click a row to view its full log in the Active Job panel.

Columns: ID (truncated), Profile, Table, Status, Started, Finished.

### Config editor

Click the **⚙ Config** button (bottom-right) to open a modal form for editing the active profile's src/dst settings. Leave password fields empty to keep existing passwords. Changes are validated server-side before saving.

---

## API endpoints

The dashboard is backed by a REST API:

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/status` | `[InstanceStatus, InstanceStatus]` |
| `GET` | `/api/tables` | `[TableRow, ...]` diff |
| `POST` | `/api/copy` | Start copy job → `{job_id}` |
| `GET` | `/api/jobs` | List recent jobs |
| `GET` | `/api/jobs/{id}` | Job detail with log lines |
| `GET` | `/api/jobs/{id}/stream` | SSE stream of log lines |
| `GET` | `/api/config` | Current profile (passwords masked) |
| `PUT` | `/api/config` | Update profile fields |

---

## Dark mode

Toggle dark mode with the moon/sun button in the top-right corner. The preference is stored in `localStorage`.
