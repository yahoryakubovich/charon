# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-29

### Added
- Initial release
- CLI commands: `config`, `status`, `list`, `diff`, `copy`, `web`
- Web dashboard with diff view, live copy progress (SSE), job history, config editor
- Partition-aware copy via `INSERT INTO FUNCTION remote()`
- Conventional Commits + GitHub Actions CI/CD pipeline
