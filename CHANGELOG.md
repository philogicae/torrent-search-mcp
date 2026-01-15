## [2.0.2] - 2026-01-15

### ⚙️ Miscellaneous Tasks

- Chore: update changelog format and disable conventional commits in cliff.toml

- Regenerate CHANGELOG.md with detailed commit message bodies
- Switch from conventional commits to full message parsing
- Change "Other" category to "Changes" in commit parser
- Remove markdown formatting from changelog header
- Chore: bump version to 2.0.2 and improve CLI output formatting

- Update version from 2.0.1 to 2.0.2 in pyproject.toml
- Remove redundant debug prints for sources and torrent count
- Consolidate CLI output into single formatted line showing excluded sources, found sources, and torrent count

## [2.0.1] - 2026-01-13

### ⚙️ Miscellaneous Tasks

- Chore: release version 2.0.0 with La Cale tracker support and API improvements
- Chore: bump version to 2.0.1 with configuration and testing improvements

- Rename `YGG_BASE_URL` to `YGG_LOCAL_API` for clarity
- Remove unused `LA_CALE_TRACKER` environment variable
- Clean up cliff.toml changelog template formatting
- Add `YGG_LOCAL_API` to docker-compose environment
- Parallelize torrent searches using asyncio gather
- Fix source filtering logic and improve CLI output
- Enhance regex patterns for better torrent data extraction
- Update tests with separate cases for ThePirateBay and Nyaa

## [2.0.0] - 2026-01-12

### 📚 Documentation

- Docs: update README and changelog for La Cale tracker support and API changes

- Add La Cale as fourth supported tracker alongside ThePirateBay, Nyaa, and YggTorrent
- Update configuration section to include La Cale passkey and YggTorrent username/password
- Document consolidated API endpoints: `/torrent/search` and `/torrent/{torrent_id}`
- Remove references to deprecated `get_torrent_info` tool
- Add `data://torrent_sources` resource documentation
- Update MCP client configuration examples with

### ⚙️ Miscellaneous Tasks

- Chore: update changelog for v1.11.2 release with lxml system dependencies
- Chore: major refactor to v2.0.0 with multi-tracker support and API improvements

- Add LaCale tracker configuration alongside YggTorrent
- Replace mypy with ty for type checking across CI and dev workflows
- Rename API endpoints: `/torrents/search` → `/torrent/search`, merge detail/download endpoints
- Consolidate `get_torrent_details()` and `get_magnet_link_or_torrent_file()` into single `get_torrent()` method
- Remove `prepare_search_query` tool, integrate query preparation into `search_torrents`

## [1.11.2] - 2025-11-28

### ⚙️ Miscellaneous Tasks

- Ci: add system dependencies for lxml and bump version to 1.11.2

## [1.11.1] - 2025-09-30

### ⚙️ Miscellaneous Tasks

- Chore: bump version from 1.11.0 to 1.11.1
- Chore: bump version to 1.11.1 and update changelog

## [1.11.0] - 2025-08-25

### ⚙️ Miscellaneous Tasks

- Chore: update dependencies
- Chore: update changelog for v1.11.0 release with dependency updates

## [1.10.2] - 2025-08-16

### ⚙️ Miscellaneous Tasks

- Chore: update deps
- Chore: update changelog for v1.10.2 release with dependency updates

## [1.10.0] - 2025-08-06

### ⚙️ Miscellaneous Tasks

- Ci: add Docker Hub publishing workflow and container configuration
- Chore: update changelog for v1.10.0 release with Docker Hub workflow

## [1.9.2] - 2025-08-04

### ⚙️ Miscellaneous Tasks

- Chore: update dependencies
- Chore: update changelog for v1.9.2 release

## [1.9.1] - 2025-07-20

### ⚙️ Miscellaneous Tasks

- Chore: downgrade crawl4ai to 0.6.3 and remove unused dependencies
- Chore: downgrade crawl4ai to 0.6.3 and cleanup dependencies

## [1.9.0] - 2025-07-20

### 🚀 Features

- Feat: update search query preparation and result prioritization logic

### 📚 Documentation

- Docs: update changelog for v1.9.0 with search improvements and dependency updates

### ⚙️ Miscellaneous Tasks

- Chore: update aiohttp from 3.12.13 to 3.12.14 and adjust Python version requirements

## [1.8.2] - 2025-07-06

### 🚀 Features

- Feat: add empty results handling in torrent search response

### 📚 Documentation

- Docs: update changelog for v1.8.2 with empty results handling and workflow optimizations

### ⚙️ Miscellaneous Tasks

- Ci: optimize GitHub Actions workflow with uv caching and tag-based releases

## [1.8.1] - 2025-07-03

### 🐛 Bug Fixes

- Fix: handle torrent file download failures and improve filepath handling

### 📚 Documentation

- Docs: add changelog entries for v1.8.0 release
- Docs: add changelog entries for v1.8.1 release with bug fixes and documentation updates

## [1.8.0] - 2025-07-02

### 🚀 Features

- Feat: add support for downloading torrent files as alternative to magnet links

### 🐛 Bug Fixes

- Fix: handle case-insensitive INCLUDE_MAGNET_LINKS env var and make YggTorrent optional
- Fix: update dependencies, fix tests, update readme instructions

### 🚜 Refactor

- Refactor: optimize Dockerfile with multi-stage builds and improved caching

### 📚 Documentation

- Docs: update tool names and descriptions to be more generic and consistent
- Docs: update installation instructions and default server configurations

## [1.7.0] - 2025-06-26

### 🚜 Refactor

- Refactor: rename get_torrent_details to get_torrent_info for consistency

### 📚 Documentation

- Docs: update changelog for v1.7.0 with renamed torrent function

## [1.6.0] - 2025-06-24

### ⚙️ Miscellaneous Tasks

- Chore: upgrade dependencies including fastmcp to 2.9.0 and litellm to 1.73.1
- Chore: update changelog for v1.6.0 with dependency upgrades

## [1.5.0] - 2025-06-22

### 🚀 Features

- Feat: add prepare_search_query tool

### ⚙️ Miscellaneous Tasks

- Chore: update dependencies and changelog for version 1.4.1
- Chore: update dependencies (numpy 2.3.1, litellm 1.73.0, hf-xet 1.1.5)
- Chore: update changelog for v1.5.0 with new search query tool and dependency updates

## [1.4.1] - 2025-06-19

### ⚙️ Miscellaneous Tasks

- Chore: update litellm to 1.72.6.post2 and ygg-torrent-mcp to 1.5.0

## [1.4.0] - 2025-06-19

### 🚀 Features

- Feat: implement caching and base62 compression for torrent IDs

### ⚙️ Miscellaneous Tasks

- Chore: bump version to 1.4.0 for caching and base62 compression features

## [1.3.0] - 2025-06-17

### 🚜 Refactor

- Refactor: rework on api/mcp logic to simplify params, optimize prompts, and reduce overall token consumption
- Refactor: simplify Dockerfile by using single-stage build

### 📚 Documentation

- Docs: update changelog for v1.3.0 with API refactoring and dependency updates

### ⚙️ Miscellaneous Tasks

- Chore: update ygg dependencies and version

## [1.2.0] - 2025-06-17

### 🚀 Features

- Feat: implement torrent caching and unified torrent ID system across sources [wrapper]
- Feat: implement torrent caching and unified torrent ID system across sources [servers]

### 💼 Changes

- Minor fixes

### 📚 Documentation

- Docs: update changelog for v1.2.0 with caching and unified torrent ID features

### 🧪 Testing

- Tests: add max_items parameter to search_torrents tool

### ⚙️ Miscellaneous Tasks

- Chore: bump version from 1.1.4 to 1.2.0

## [1.1.4] - 2025-06-15

### 🚜 Refactor

- Refactor: simplify MCP server with default sources and improve search guidelines

### 📚 Documentation

- Docs: update changelog for v1.1.4 with refactoring changes

## [1.1.3] - 2025-06-15

### 🚀 Features

- Feat: update server instructions and improve torrent search API documentation

### 🐛 Bug Fixes

- Fix: typo
- Fix: suppress crawl4ai deprecation warnings and reorder imports

### 📚 Documentation

- Docs: update changelog for v1.1.3 with new features and bug fixes

## [1.1.2] - 2025-06-13

### 🐛 Bug Fixes

- Fix: update badge URLs with proper cache control parameters

### 📚 Documentation

- Docs: add uv, Python version and CI status badges to README
- Docs: add project badges and update dependencies in README

### ⚙️ Miscellaneous Tasks

- Chore: update dependencies and remove unused requirements

## [1.1.1] - 2025-06-12

### 🚀 Features

- Feat: add root user detection for playwright driver installation with dependencies

### 💼 Changes

- Changelog 1.1.1

## [1.1.0] - 2025-06-12

### 🚀 Features

- Feat: add type hints and improve code quality with mypy

### 📚 Documentation

- Docs: add glama.json and update README with no-sudo MCP server config

### ⚙️ Miscellaneous Tasks

- Chore: bump version to 1.1.0
- Chore: update CHANGELOG for v1.1.0 with type hints and documentation improvements

## [1.0.0] - 2025-06-11

### 🚀 Features

- Feat: wrapper
- Feat: mcp server + fastapi
- Feat: tests
- Feat: docker setup

### 💼 Changes

- Init
- Pyproject setup

### 📚 Documentation

- Docs: readme + .env.example
- Docs: add CHANGELOG.md to track project changes and releases

### ⚙️ Miscellaneous Tasks

- Ci: add playwright installation and update build process with uv
