# Changelog

All notable changes to this project will be documented in this file.

## [1.9.2] - 2025-08-04

### ⚙️ Miscellaneous Tasks

- Update dependencies

## [1.9.1] - 2025-07-20

### ⚙️ Miscellaneous Tasks

- Downgrade crawl4ai to 0.6.3 and remove unused dependencies
- Downgrade crawl4ai to 0.6.3 and cleanup dependencies

## [1.9.0] - 2025-07-20

### 🚀 Features

- Update search query preparation and result prioritization logic

### 📚 Documentation

- Update changelog for v1.9.0 with search improvements and dependency updates

### ⚙️ Miscellaneous Tasks

- Update aiohttp from 3.12.13 to 3.12.14 and adjust Python version requirements

## [1.8.2] - 2025-07-06

### 🚀 Features

- Add empty results handling in torrent search response

### 📚 Documentation

- Update changelog for v1.8.2 with empty results handling and workflow optimizations

### ⚙️ Miscellaneous Tasks

- Optimize GitHub Actions workflow with uv caching and tag-based releases

## [1.8.1] - 2025-07-03

### 🐛 Bug Fixes

- Handle torrent file download failures and improve filepath handling

### 📚 Documentation

- Add changelog entries for v1.8.0 release
- Add changelog entries for v1.8.1 release with bug fixes and documentation updates

## [1.8.0] - 2025-07-02

### 🚀 Features

- Add support for downloading torrent files as alternative to magnet links

### 🐛 Bug Fixes

- Handle case-insensitive INCLUDE_MAGNET_LINKS env var and make YggTorrent optional
- Update dependencies, fix tests, update readme instructions

### 🚜 Refactor

- Optimize Dockerfile with multi-stage builds and improved caching

### 📚 Documentation

- Update tool names and descriptions to be more generic and consistent
- Update installation instructions and default server configurations

## [1.7.0] - 2025-06-26

### 🚜 Refactor

- Rename get_torrent_details to get_torrent_info for consistency

### 📚 Documentation

- Update changelog for v1.7.0 with renamed torrent function

## [1.6.0] - 2025-06-24

### ⚙️ Miscellaneous Tasks

- Upgrade dependencies including fastmcp to 2.9.0 and litellm to 1.73.1
- Update changelog for v1.6.0 with dependency upgrades

## [1.5.0] - 2025-06-22

### 🚀 Features

- Add prepare_search_query tool

### ⚙️ Miscellaneous Tasks

- Update dependencies and changelog for version 1.4.1
- Update dependencies (numpy 2.3.1, litellm 1.73.0, hf-xet 1.1.5)
- Update changelog for v1.5.0 with new search query tool and dependency updates

## [1.4.1] - 2025-06-19

### ⚙️ Miscellaneous Tasks

- Update litellm to 1.72.6.post2 and ygg-torrent-mcp to 1.5.0

## [1.4.0] - 2025-06-19

### 🚀 Features

- Implement caching and base62 compression for torrent IDs

### ⚙️ Miscellaneous Tasks

- Bump version to 1.4.0 for caching and base62 compression features

## [1.3.0] - 2025-06-17

### 🚜 Refactor

- Rework on api/mcp logic to simplify params, optimize prompts, and reduce overall token consumption
- Simplify Dockerfile by using single-stage build

### 📚 Documentation

- Update changelog for v1.3.0 with API refactoring and dependency updates

### ⚙️ Miscellaneous Tasks

- Update ygg dependencies and version

## [1.2.0] - 2025-06-17

### 🚀 Features

- Implement torrent caching and unified torrent ID system across sources [wrapper]
- Implement torrent caching and unified torrent ID system across sources [servers]

### 📚 Documentation

- Update changelog for v1.2.0 with caching and unified torrent ID features

### 🧪 Testing

- Add max_items parameter to search_torrents tool

### ⚙️ Miscellaneous Tasks

- Bump version from 1.1.4 to 1.2.0

## [1.1.4] - 2025-06-15

### 🚜 Refactor

- Simplify MCP server with default sources and improve search guidelines

### 📚 Documentation

- Update changelog for v1.1.4 with refactoring changes

## [1.1.3] - 2025-06-15

### 🚀 Features

- Update server instructions and improve torrent search API documentation

### 🐛 Bug Fixes

- Typo
- Suppress crawl4ai deprecation warnings and reorder imports

### 📚 Documentation

- Update changelog for v1.1.3 with new features and bug fixes

## [1.1.2] - 2025-06-13

### 🐛 Bug Fixes

- Update badge URLs with proper cache control parameters

### 📚 Documentation

- Add uv, Python version and CI status badges to README
- Add project badges and update dependencies in README

### ⚙️ Miscellaneous Tasks

- Update dependencies and remove unused requirements

## [1.1.1] - 2025-06-12

### 🚀 Features

- Add root user detection for playwright driver installation with dependencies

## [1.1.0] - 2025-06-12

### 🚀 Features

- Add type hints and improve code quality with mypy

### 📚 Documentation

- Add glama.json and update README with no-sudo MCP server config

### ⚙️ Miscellaneous Tasks

- Bump version to 1.1.0
- Update CHANGELOG for v1.1.0 with type hints and documentation improvements

## [1.0.0] - 2025-06-11

### 🚀 Features

- Wrapper
- Mcp server + fastapi
- Tests
- Docker setup

### 📚 Documentation

- Readme + .env.example
- Add CHANGELOG.md to track project changes and releases

### ⚙️ Miscellaneous Tasks

- Add playwright installation and update build process with uv

<!-- generated by git-cliff -->
