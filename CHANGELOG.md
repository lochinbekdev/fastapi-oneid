# Changelog

All notable changes to `fastapi-oneid` will be documented in this file.

## Unreleased

- Added official OneID security flow with generated and verified OAuth state
- Enforced redirect URI whitelist and disabled loopback redirect URIs
- Added typed token, user-info, logout, and auth payload schemas
- Added logout client and API endpoint support
- Hardened error handling, default timeout, and raw payload exposure rules
- Expanded tests and README for the official OneID technological guide

## 0.1.0 - 2026-04-27

- Initial public release
- OneID authorization URL generation
- OneID code-to-token exchange
- OneID access-token-to-user resolution
- FastAPI web and API router helpers
- Consumer-side authentication handler support
- Unit tests, release metadata, and PyPI-ready packaging
