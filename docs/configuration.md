# Configuration Reference

charon stores all configuration in `~/.charon/config.yaml`. The file is created with permissions `0600` (owner-read-write only) to protect passwords.

## File structure

```yaml
default_profile: default

profiles:
  default:
    src:
      host: http://clickhouse-src:8123
      user: default
      password: ""
      database: mydb
      timeout: 3600
    dst:
      host: http://clickhouse-dst:8123
      user: default
      password: ""
      database: mydb
      timeout: 3600
      tcp_hostport: clickhouse-dst:9000
    copy_by_partitions: true
    copy_views: false
    copy_kafka_tables: false
    copy_dictionaries: false
    convert_replicated_to_merge: false
    skip_tables: []
    retry_count: 3
    retry_sleep: 2.0
    retry_max_sleep: 30.0
    insert_settings:
      max_partitions_per_insert_block: 1000
      max_insert_block_size: 1048576
      max_threads: 8
      send_logs_level: warning
```

---

## Top-level fields

| Field | Type | Default | Description |
|---|---|---|---|
| `default_profile` | string | `"default"` | Profile used when `--profile` is not specified |
| `profiles` | map | `{}` | Named profiles |

---

## InstanceConfig fields (src / dst)

| Field | Type | Default | Description |
|---|---|---|---|
| `host` | string | required | HTTP URL. Bare hostnames are auto-prefixed with `http://`. |
| `user` | string | `"default"` | ClickHouse username |
| `password` | string | `""` | Password (never logged or printed) |
| `database` | string | required | Database name |
| `timeout` | int | `3600` | HTTP request timeout in seconds |
| `tcp_hostport` | string | `null` | `host:port` for TCP — required by `remote()` INSERT on dst |

---

## CopyProfile fields

### Copy behaviour

| Field | Type | Default | Description |
|---|---|---|---|
| `copy_by_partitions` | bool | `true` | Copy partition-by-partition. Requires `dst.tcp_hostport`. |
| `copy_views` | bool | `false` | Copy VIEW tables |
| `copy_kafka_tables` | bool | `false` | Copy Kafka / RabbitMQ / NATS engine tables |
| `copy_dictionaries` | bool | `false` | Copy Dictionary tables |
| `convert_replicated_to_merge` | bool | `false` | Strip `Replicated` prefix from engine names in DDL |
| `skip_tables` | list[string] | `[]` | Tables to skip entirely |

### Retry

| Field | Type | Default | Description |
|---|---|---|---|
| `retry_count` | int | `3` | Max number of attempts per query |
| `retry_sleep` | float | `2.0` | Base sleep time in seconds (doubles each attempt) |
| `retry_max_sleep` | float | `30.0` | Maximum sleep cap for backoff |

Backoff formula: `sleep = min(retry_sleep * 2^attempt, retry_max_sleep)` + ±10% jitter.

### insert_settings

Passed as ClickHouse HTTP settings on INSERT queries.

| Field | Type | Default | Description |
|---|---|---|---|
| `max_partitions_per_insert_block` | int | `1000` | |
| `max_insert_block_size` | int | `1048576` | |
| `max_threads` | int | `8` | |
| `send_logs_level` | string | `"warning"` | |

---

## Multiple profiles example

```yaml
default_profile: prod

profiles:
  dev:
    src:
      host: http://ch-dev:8123
      database: analytics
    dst:
      host: http://ch-dev-replica:8123
      database: analytics
      tcp_hostport: ch-dev-replica:9000

  prod:
    src:
      host: http://ch-prod:8123
      user: reader
      password: s3cr3t
      database: analytics
    dst:
      host: http://ch-prod-replica:8123
      user: writer
      password: wr1t3r
      database: analytics
      tcp_hostport: ch-prod-replica:9000
    retry_count: 5
    retry_sleep: 3.0
```

Switch profiles with `--profile dev` or set `CHCOPY_PROFILE=dev`.
