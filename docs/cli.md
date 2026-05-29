# CLI Reference

## Global options

These options can be passed before any sub-command:

| Option | Env var | Description |
|---|---|---|
| `--config PATH` | `CHCOPY_CONFIG` | Config file path (default: `~/.charon/config.yaml`) |
| `--profile NAME` | `CHCOPY_PROFILE` | Profile to use (default: `default_profile` in config) |
| `--version` | — | Print version and exit |

---

## charon config

### `charon config init`

Interactive wizard to create or update a profile.

```bash
charon config init
charon config init --profile staging
```

Prompts for src/dst host, user, password, database, and TCP hostport.
Saves with `chmod 0600`.

### `charon config show`

Print the active profile. Passwords are always shown as `***`.

```bash
charon config show
charon config show --profile prod
```

### `charon config list`

List all profile names.

```bash
charon config list
```

### `charon config delete PROFILE`

Remove a profile. Asks for confirmation unless `--yes` is passed.

```bash
charon config delete staging
charon config delete staging --yes
```

---

## charon status

Ping both src and dst and show aggregate stats (table count, total rows, total bytes).

```bash
charon status
charon status --profile prod
```

Output: two side-by-side panels with connectivity indicator (green/red).

---

## charon list

List tables on src (default) or dst.

```bash
# List source tables
charon list

# List destination tables
charon list --dst

# Filter by regex
charon list --filter "^event_"
charon list --dst --filter "log"
```

Columns: name, engine, total_rows, total_bytes, DDL (truncated).

---

## charon diff

Show row-count difference between src and dst.

```bash
# Table-level summary
charon diff

# Partition-level detail for one table
charon diff --table my_table

# Machine-readable JSON
charon diff --json
charon diff --table my_table --json
```

Status codes:
- `ok` — row counts match
- `mismatch` — row counts differ
- `missing` — table/partition absent on dst

---

## charon copy

Copy tables from src to dst.

```bash
# Copy everything
charon copy

# Copy a single table
charon copy --table events

# Copy specific tables
charon copy --tables "events,users,sessions"

# Dry run (show what would be copied)
charon copy --dry-run

# Copy without partition awareness (full table INSERT)
charon copy --no-partitions

# Combine options
charon copy --table events --dry-run --profile prod
```

| Option | Default | Description |
|---|---|---|
| `--table NAME` | — | Copy one table |
| `--tables T1,T2` | — | Copy comma-separated list |
| `--dry-run` | false | Show plan without executing |
| `--no-partitions` | false | Skip partition-aware copy |

Shows Rich progress bars with overall and per-table progress. Prints a summary table at the end.

---

## charon web

Start the web dashboard.

```bash
charon web
charon web --port 9000
charon web --host 0.0.0.0 --port 8080
charon web --reload   # dev mode
```

| Option | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Port |
| `--reload` | false | Auto-reload on code changes |

Open `http://localhost:8765` in your browser.
