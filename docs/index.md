# charon

**charon** is a ClickHouse database copier with a CLI and web dashboard.

It copies tables between ClickHouse instances partition-by-partition using `INSERT INTO FUNCTION remote()`, tracks jobs, and shows a live diff between source and destination.

## Features

- Partition-aware copy — no intermediate files, no large single queries
- Schema DDL sync with `ON CLUSTER` stripping and Replicated→plain engine conversion
- Live diff: table-level and partition-level row-count comparison
- Web dashboard with SSE log streaming
- Job history in SQLite
- Configurable retry with exponential backoff
- Multiple named profiles in `~/.charon/config.yaml`
- Dry-run mode

## Pages

- [Configuration Reference](configuration.md) — all config fields with types and defaults
- [CLI Reference](cli.md) — all CLI commands with examples
- [Web Dashboard](web.md) — web UI usage guide

## Quick start

```bash
pip install charon
charon config init
charon status
charon diff
charon copy
```
