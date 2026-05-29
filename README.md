# charon

[![PyPI version](https://img.shields.io/pypi/v/charon.svg)](https://pypi.org/project/charon/)
[![CI](https://github.com/your-org/charon/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/charon/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**charon** is a ClickHouse database copier with a CLI and web dashboard. It copies tables between ClickHouse instances partition-by-partition, shows a live diff, and tracks job history.

---

## Features

- Partition-aware copy using `INSERT INTO FUNCTION remote()` — no intermediate files
- Schema DDL sync: tables, views, materialized views, dictionaries (optional)
- Live diff: compare source vs. destination row counts per partition
- Web dashboard with SSE live log streaming
- Job history persisted to SQLite
- Configurable retry with exponential backoff
- Multiple named profiles in `~/.charon/config.yaml`
- Replicated engine → plain engine conversion option
- Dry-run mode
- `ON CLUSTER` clause stripping for single-node destinations

---

## Installation

```bash
# Using pipx (recommended for end-users)
pipx install charon

# Using uv tool
uv tool install charon
```

---

## Quick start

```bash
# Initialize a profile interactively
charon config init

# Check connectivity
charon status

# List tables on the source
charon list

# Show row-count diff between src and dst
charon diff

# Copy everything
charon copy

# Copy a single table
charon copy --table my_table

# Dry run
charon copy --dry-run

# Start the web dashboard
charon web
```

---

## CLI Reference

### `charon config init`
Interactive wizard that creates or updates a named profile.

### `charon config show [--profile NAME]`
Print the current profile (password masked).

### `charon config list`
List all profile names.

### `charon config delete PROFILE`
Remove a profile.

### `charon status [--profile NAME]`
Ping source and destination; show table count, total rows, total bytes.

### `charon list [--src|--dst] [--filter REGEX]`
List tables on source or destination with engine, row count, and byte size.

### `charon diff [--table TABLE] [--json]`
Compare source and destination. Without `--table`: table-level summary. With `--table`: partition-level detail.

### `charon copy [OPTIONS]`

| Option | Default | Description |
|---|---|---|
| `--table TABLE` | — | Copy a single table |
| `--tables T1,T2` | — | Copy specific tables |
| `--dry-run` | false | Show what would be copied |
| `--no-partitions` | false | Copy whole table at once |
| `--profile NAME` | default | Profile to use |

### `charon web [OPTIONS]`

| Option | Default | Description |
|---|---|---|
| `--host` | 127.0.0.1 | Bind address |
| `--port` | 8765 | Port |
| `--reload` | false | Auto-reload (dev mode) |

---

## Configuration reference

Config file: `~/.charon/config.yaml` (permissions: 0600)

```yaml
default_profile: prod

profiles:
  prod:
    src:
      host: http://clickhouse-src:8123
      user: default
      password: secret
      database: analytics
      timeout: 3600
    dst:
      host: http://clickhouse-dst:8123
      user: default
      password: secret
      database: analytics
      tcp_hostport: clickhouse-dst:9000   # required for remote() INSERT
    copy_by_partitions: true
    copy_views: false
    copy_kafka_tables: false
    copy_dictionaries: false
    convert_replicated_to_merge: false
    skip_tables:
      - huge_log_table
    retry_count: 3
    retry_sleep: 2.0
    retry_max_sleep: 30.0
    insert_settings:
      max_partitions_per_insert_block: 1000
      max_insert_block_size: 1048576
      max_threads: 8
      send_logs_level: warning
```

### Field descriptions

| Field | Type | Default | Description |
|---|---|---|---|
| `src.host` | str | required | HTTP URL of source CH (auto-prefixed with `http://`) |
| `src.user` | str | `default` | Username |
| `src.password` | str | `""` | Password (never logged) |
| `src.database` | str | required | Source database name |
| `src.timeout` | int | 3600 | Request timeout in seconds |
| `dst.tcp_hostport` | str | None | `host:port` for TCP — required by `remote()` INSERT |
| `copy_by_partitions` | bool | true | Copy partition-by-partition |
| `copy_views` | bool | false | Also copy VIEW tables |
| `copy_kafka_tables` | bool | false | Also copy Kafka engine tables |
| `copy_dictionaries` | bool | false | Also copy Dictionary tables |
| `convert_replicated_to_merge` | bool | false | Strip Replicated* prefix in DDL |
| `skip_tables` | list[str] | `[]` | Tables to skip |
| `retry_count` | int | 3 | Max retry attempts |
| `retry_sleep` | float | 2.0 | Base sleep between retries (seconds) |
| `retry_max_sleep` | float | 30.0 | Cap for exponential backoff |

---

## Web dashboard

Open [http://localhost:8765](http://localhost:8765) after running `charon web`.

Features:
- Live status cards for src and dst
- Table comparison grid with color-coded diff
- One-click copy (all or selected tables)
- SSE log stream for running jobs
- Job history (last 20 jobs)
- Profile config editor

---

## Development setup

```bash
git clone https://github.com/your-org/charon
cd charon
uv sync --all-extras
```

### Available make targets

```bash
make install      # uv sync --all-extras
make lint         # ruff check + format check
make typecheck    # mypy
make test         # pytest
make test-cov     # pytest with coverage
make build        # uv build
make clean        # remove dist/, .venv/, caches
```

---

## Contributing

### Branches

| Branch | Purpose |
|--------|---------|
| `main` | Protected. Releases happen here. Only via PR. |
| `feat/<name>` | New feature — branch off `main`, PR back to `main` |
| `fix/<name>` | Bug fix — same flow |
| `chore/<name>` | Maintenance, deps, tooling |

```bash
git checkout -b feat/profile-switcher
# ... work ...
git push origin feat/profile-switcher
# open PR → CI runs → merge → automatic release
```

### Commit messages — Conventional Commits

Format: `<type>(<optional scope>): <description>`

| Type | When to use | Version bump |
|------|-------------|-------------|
| `feat:` | New feature | `minor` — `0.1.0 → 0.2.0` |
| `fix:` | Bug fix | `patch` — `0.1.0 → 0.1.1` |
| `feat!:` or `BREAKING CHANGE:` in body | Breaking API change | `major` — `0.1.0 → 1.0.0` |
| `docs:` | Documentation only | no bump |
| `chore:` | Deps, tooling, housekeeping | no bump |
| `ci:` | CI/CD changes | no bump |
| `refactor:` | Code restructure, no behaviour change | no bump |
| `test:` | Adding or fixing tests | no bump |
| `perf:` | Performance improvement | `patch` |

Examples:

```
feat: add profile switcher in web UI
fix: handle empty partition list on first sync
feat(web)!: rename /api/config to /api/settings
docs: add TCP hostport explanation to README
chore: bump fastapi to 0.115
```

### Release cycle (fully automated)

When a PR is merged to `main`, GitHub Actions:

1. Runs lint + typecheck + tests
2. `python-semantic-release` reads all commits since the last tag
3. Determines the next version (`major` / `minor` / `patch`)
4. Bumps `version` in `pyproject.toml` and `charon/__init__.py`
5. Updates `CHANGELOG.md`
6. Creates a git tag `vX.Y.Z` and a GitHub Release
7. Publishes the package to PyPI

> If there are no `feat:` or `fix:` commits (only `chore:`, `docs:`, etc.) — no release is created.

### Required secrets (GitHub → Settings → Secrets)

| Secret | Value |
|--------|-------|
| `PYPI_TOKEN` | API token from pypi.org |
| `GH_TOKEN` | GitHub PAT with `contents: write` scope |

---

## License

MIT — see [LICENSE](LICENSE).
