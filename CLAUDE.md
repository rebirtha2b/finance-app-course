# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All Python commands run from `backend/` using the checked-out venv at `backend/.venv`:

```bash
cd backend
.venv/Scripts/python -m pytest                          # all tests (Windows)
.venv/Scripts/python -m pytest tests/test_portfolio.py   # one file
.venv/Scripts/python -m pytest tests/test_portfolio.py::test_name   # one test
.venv/Scripts/python -m pytest -k "stale"                # by name pattern

.venv/Scripts/python -m uvicorn app.main:app             # serves API + built UI on :8000
.venv/Scripts/python -m uvicorn app.main:app --reload     # backend dev

.venv/Scripts/python -m alembic revision --autogenerate -m "what changed"
.venv/Scripts/python -m alembic upgrade head
```

Frontend, from `frontend/`:

```bash
npm run dev     # Vite on :5173, proxies /api to :8000
npm run build   # tsc -b && vite build -> frontend/dist
npm run lint    # oxlint
```

There is no frontend test suite. `npm run build` (which type-checks via `tsc -b`) plus `npm run lint` are the frontend verification steps.

**After changing frontend code, run `npm run build`** or the backend keeps serving the previous bundle from `frontend/dist`.

## Architecture

Single-user local app: FastAPI backend + React SPA, one SQLite file at `data/finance.db`. In production `app.main` mounts `frontend/dist` at `/` via `SPAStaticFiles`, so one process serves both. That mount catches everything the API routers didn't match, hence the explicit `/api/` 404 guard in `SPAStaticFiles.get_response` — without it a typo'd endpoint returns HTML with status 200.

Layering: `api/` (routers, thin) → `services/` (all business logic) → `models/` (SQLAlchemy) . `schemas/` holds Pydantic request/response models. Put logic in `services/`; routers should validate, delegate, and map to schemas.

- **`app/money.py`** — the money contract. Read it before touching any amount.
- **`app/services/prices/`** — the only place that touches the network. `get_provider()` / `set_provider()` is the seam; adding a data source means one new `PriceProvider` subclass.
- **`app/services/scheduler.py`** — in-process APScheduler. Recurring generation at 00:05, price refresh at `FINANCE_PRICE_FETCH_HOUR` (default 23). Both jobs are catch-up based and also run on startup, so missing a window is harmless. Both swallow exceptions: a failing background job must never take the app down.
- **`app/config.py`** — `Settings` with `FINANCE_` env prefix, `.env` at repo root. `settings.enable_scheduler=False` for scripts/tests.

Frontend: `src/api/client.ts` is the single typed API surface (all `fetch` lives there, plus `ApiError` unwrapping FastAPI's `detail`); `src/api/types.ts` mirrors backend schemas; `src/api/money.ts` handles all display formatting and input parsing. Pages under `src/pages/` map 1:1 to nav routes in `App.tsx`, which also owns the single-key shortcuts (`d`/`t`/`s`/`b`/`p`/`r`).

## Invariants

These are load-bearing — code and tests depend on them, and several exist because the naive alternative produced a specific bug.

- **Money is integer cents in the DB, `Decimal` in Python, and a JSON *string* over the wire.** Never `float`, never a JSON number (JS parses those as doubles, reintroducing the imprecision). Share quantities and unit prices use `ExactDecimal` (text-backed) because SQLAlchemy's `Numeric` round-trips through float on SQLite.
- **Transaction amounts are signed**: expenses negative, income positive. Budget limits are always positive magnitudes; spend is the negation of the sum, so refunds correctly give budget back.
- **Category filters and budgets include child categories.** Two levels only (parent + leaves).
- **Recurring generation is idempotent** — skipped by existing due date, backstopped by `UNIQUE(recurring_rule_id, due_date)`. Occurrences are always computed from the rule's `start_date`, never from the previous occurrence, so a rule on the 31st goes Jan 31 → Feb 28 → Mar 31. `due_date` stays pinned to the schedule even if the user edits the actual `date`.
- **A failed price fetch never shows zero.** Fall back to the last stored close and mark it stale; a never-priced holding shows blank values, not 0. Portfolio total gain is summed from per-holding gains, *not* `total_value - total_cost` — those diverge when only some holdings have an average cost.
- **FX and price lookups take the most recent row on or before the date**, so weekends and holidays resolve instead of failing.
- SQLite needs `PRAGMA foreign_keys=ON` explicitly (set in `app/db.py`, mirrored in the test `engine` fixture) — otherwise `ondelete` clauses silently do nothing.

## Tests

`tests/conftest.py` gives every test an in-memory SQLite DB with the real schema (`StaticPool`, since `TestClient` runs on another thread). The `client` fixture overrides `get_session` and is deliberately **not** used as a context manager — running the app lifespan would seed the real `data/finance.db`. A `fake_prices` autouse fixture swaps in `tests/fake_provider.FakeProvider` for every test, so nothing ever reaches real yfinance; tests that care about prices script that fixture.

`data/finance.db` is gitignored on purpose — real financial data must not reach version control.

## Reference

`PRD.md` is the full specification (all 7 phases complete). `README.md` covers setup, config vars, CSV import behaviour, and ticker format (Yahoo symbols: `AAPL`, `SAP.DE`, `ASML.AS`).
