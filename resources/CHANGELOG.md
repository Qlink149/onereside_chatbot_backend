# Changelog

All notable changes to OneReside Bot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<img src="assets/hue-bar.svg" width="100%" height="4" alt=""/>

## [2026-07-22]

### Added
- `DELETE /system/users/{user_id}` to delete a user's profile (orders/payments are preserved).
- Admin activity logging, backed by a new `admin_logs` collection.
- `GET /system/admin-logs` to list admin activity logs.
