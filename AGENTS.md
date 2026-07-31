# Project Instructions

## Marketplace Isolation Rule

When a request mentions a specific marketplace, changes must be scoped to that marketplace only.

Examples:

- A Leroy Merlin fix must not change Carrefour or Worten behavior.
- A Carrefour scraper change must not alter Leroy warm-up, Leroy cache, or Worten flow.
- A Worten anti-bot or extraction change must stay inside Worten-specific logic.

Before editing, identify the marketplace affected and the exact boundary:

- marketplace config in `marketplaces.py`;
- checker class or methods in `dashboard_leroy.py`;
- dashboard controls/state in `dashboard_leroy_modern.py`;
- cache/feed paths under `fase1/`;
- local profile paths under `fase1/`.

Shared code may be changed only when the request explicitly affects all marketplaces or when the shared change is necessary. If shared code is touched, verify and document the impact on every marketplace.

For profile, cookie, warm-up, anti-bot, retry, cache, batch size, extraction, or classification changes, prefer marketplace-specific subclasses, config keys, paths, and guards.

Do not rotate, delete, clean, or migrate profiles/caches for unrelated marketplaces.
