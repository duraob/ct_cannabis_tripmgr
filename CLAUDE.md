# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Middleware that bridges **LeafTrade** (customer orders) and **BioTrack** (state cannabis traceability: drivers, vehicles, rooms, vendors, inventory). Users group LeafTrade orders into delivery trips, assign 2 drivers + 1 vehicle, and execute the trip — which creates BioTrack sublots, moves inventory into the destination room, and generates a manifest per stop, with Google Maps route timing embedded in the manifest.

## Commands

```bash
source .venv/bin/activate       # always activate first (per .cursorrules)

python app.py                   # Flask app; PORT/FLASK_RUN_PORT, defaults 5000, host 0.0.0.0
python worker.py                # RQ worker — REQUIRED for trip execution and reports
redis-server                    # must be running for the worker

python create_user.py           # seed a user

flask db heads                  # ALWAYS run before creating a migration
flask db migrate -m "..."
flask db upgrade

python scripts/test_usable_weight.py   # ad-hoc verification script (no test framework in repo)
```

There is no test suite, linter, or CI configured. `scripts/` holds one-off verification scripts that hit the live APIs; run them from the project root with the venv active.

## Architecture

**`app.py` (~3200 lines) is the entire web layer** — every route, every JSON API endpoint, plus several workflow functions (`process_order_sublots`, `validate_trip`, `validate_trip_data_backend`, `_order_total_usable_weight`). There are no blueprints. Templates are server-rendered Jinja2 with Tailwind via CDN and vanilla JS calling the `/api/*` endpoints.

Layers:
- `api/biotrack.py`, `api/leaftrade.py`, `api/googlemaps_client.py` — external API clients. Method-based (except `GoogleMapsClient`), each with its own retry decorator, module-level config read from env at import time, and structured logging.
- `utils/` — `trip_execution.py` (the background job), `rpt_generation.py` (CSV reports), `task_queue.py` (RQ), `timezone.py`, `cache.py`, `inventory_types.py`, `logging_utils.py`, `log_viewer.py`.
- `models.py` — all SQLAlchemy models, single file.

### Trip execution flow

`POST /trips/<id>/execute` validates prerequisites, sets `TripExecution.status='processing'`, resets each `TripOrder.status`, then enqueues `utils.trip_execution.execute_trip_background_job` on the `trip_execution` RQ queue and redirects to `/trips/<id>/progress`. The job (30m timeout) runs under `with app.app_context()`, authenticates to BioTrack, generates/reuses Google Maps route segments into `Trip.route_data` (JSON text), then per order: fetch LeafTrade order details → bulk-create sublots → move sublots to the mapped room → `post_manifest`. Progress is written to `TripExecution.progress_message` and polled by the browser via `GET /api/trips/<id>/execution-status`. Per-order failures land in `TripOrder.error_message`; trip-level ones in `TripExecution.general_error`.

Reports (`inventory`, `finished_goods`) use the same pattern on the `report_generation` queue, but store status/filename/error as rows in `GlobalPreference` rather than a dedicated table. `worker.py` clears failed jobs and resets stuck `generating` statuses on startup.

Both queues are served by a single `SimpleWorker` in `worker.py` (SimpleWorker deliberately, for cross-platform compatibility).

### Trip state machine

Four status fields track one trip. They are **not** kept consistent by any code — know which one answers your question:

| Field | Values | Written by |
|---|---|---|
| `Trip.status` | `pending` → `validated` → `completed` / `partially_completed` / `closed` | `validate_trip` sets `validated`; the job sets `completed`/`partially_completed`; users set anything via `/trips/<id>/toggle-status` |
| `Trip.execution_status` | `pending` → `processing` → `completed` / `failed` | `execute_trip` route and the background job |
| `TripExecution.status` | same values as above | `_update_trip_execution_status` |
| `TripOrder.status` | `pending` → `sublotted` → `inventory_moved` → `manifested` | per order, inside `_process_order_manifest` |

`TripOrder.status` is the only field that reflects **what actually happened in BioTrack**. Use it — not `Trip.status` — to answer "was inventory really moved?" (`/api/trips` exposes this as `inventory_processed_in_biotrack`).

Two known sharp edges, both unresolved:

- **`Trip.execution_status` duplicates `TripExecution.status`.** Every transition writes both; the failure path in `execute_trip_background_job` writes them through separate lookups, so they can drift.
- **`Trip.status` has no transition rules.** `/trips/<id>/toggle-status` accepts any of the five values regardless of current state. A fully-manifested trip can be set back to `pending` while `execution_status` still reads `completed`, and nothing prevents re-execution — which would create **duplicate sublots and duplicate manifests** in BioTrack. Check `TripOrder.status` before re-running a trip.

### Location mapping is the linchpin

A LeafTrade order carries a `dispensary_location.id`. `LocationMapping` maps that to a BioTrack `vendor_id` + a `default_biotrack_room_id`. Without a mapping, sublot processing and trip execution fail for that order with a "No location mapping found" error. Managed at `/mapping` with CSV import/export.

### Training mode

`BIOTRACK_TRAINING_MODE` (`"1"` = training sandbox, `"0"` = production, **defaults to "1"**) is read via `app.get_training_mode()` and passed as a `training` field on every BioTrack request. `api/biotrack.py` imports it lazily from `app` inside each function — this circular-ish import is intentional; keep it lazy. It's also injected into all templates via a context processor, so the UI shows a training banner.

### Timezone

The DB stores **naive EST/EDT datetimes**, not UTC. Always use `utils/timezone.py` (`get_est_now_naive` for model defaults, `create_est_datetime_with_dst` when parsing user-entered date+time, `convert_utc_to_est` for API timestamps). Do not use `datetime.now()` or `datetime.utcnow()` directly in models or route handlers.

### Caching

Two unrelated mechanisms: `utils/cache.py` is a process-local in-memory TTL dict holding LeafTrade order details (300s) and the BioTrack full inventory sync (60s, keyed by training mode) — it is **not shared with the worker process**. `sync_inventory` returns thousands of items, so any code path needing inventory should call `get_inventory_info` and let the cache do its job rather than passing the dict around. Any BioTrack call that mutates inventory (`post_sublot_bulk_create`, `post_sublot_move`, `post_inventory_adjust`) calls `clear_inventory_cache()` on success — add that call to any new mutating function. Separately, BioTrack/LeafTrade reference data (drivers, vehicles, rooms, vendors, customers) is persisted to DB tables via the `/api/*/refresh` endpoints, with freshness tracked in `APIRefreshLog`. The `/config` page drives these refreshes — one button per type (drivers, vehicles, rooms, vendors, customers). There is deliberately **no "refresh all"**: the previous one deleted every reference row before fetching and left the DB empty when the fetch failed.

### Logging

`setup_logging()` in `app.py` installs rotating JSON-formatted handlers writing `logs/error.log`, `logs/info.log`, `logs/debug.log`. Add structured context with `logger.info(msg, extra={'extra_fields': {...}})`. `/api/error-logs` surfaces them in the UI. Console output only appears when `FLASK_DEBUG=true`.

## Conventions (from .cursorrules)

- **Method-based modules, not class-based.** Write the minimum code necessary; delete obsolete methods.
- **No fallback paths, no mock data, no backward-compatibility shims.** If an external call fails, surface the error.
- **Never create new markdown files** — no summaries, plans, changelogs, or architecture docs. Explain inline in the response instead. (This file and the existing `README.md`, `BIOTRACK_API_DOCUMENTATION.md`, `Redis_Worker_Status_Process.md` are the exceptions that already exist.)
- Migrations must form a single linear chain — check `flask db heads` first, set `down_revision` to the current head, and verify one head remains afterward.
- PEP 8; no sweeping or unrelated edits.
- UI: max 3 colors, large hit targets, sub-100ms feel with skeleton states, short URL slugs, copy in active voice.

## Environment

Required in `.env` (see `env_example.txt`, though the live `.env` has more): `DATABASE_URL` (PostgreSQL in production, SQLite fallback), `SECRET_KEY`, `REDIS_URL`, `BIOTRACK_API_URL`/`_USERNAME`/`_PASSWORD`/`_UBI`/`_TRAINING_MODE`/`_DEFAULT_LOCATION`, `LEAFTRADE_API_URL`/`_API_KEY`/`_VENDOR_ID`, `GOOGLE_MAPS_API_KEY`.

`BIOTRACK_API_DOCUMENTATION.md` documents every BioTrack function's payload shape and response format — consult it before changing `api/biotrack.py`.

## CODING AND PLANNING PROTOCOL
Behavioral guidelines to reduce common LLM coding mistakes. 
Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. 
For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" 
If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it. Don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. 
Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, 
fewer rewrites due to overcomplication, and clarifying questions come 
before implementation rather than after mistakes.