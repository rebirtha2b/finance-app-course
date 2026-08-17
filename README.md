# Finance App

Personal income, expense, and stock portfolio tracker. Runs locally as a single
process, stores everything in one SQLite file, and never sends your financial
data anywhere — the only outbound network calls are share prices and FX rates
from Yahoo Finance. See [PRD.md](PRD.md) for the full specification.

## What it does

Seven screens, all served from `http://127.0.0.1:8000`:

| Screen | What's on it |
|---|---|
| **Dashboard** (`/dashboard`) | Net worth (cash + portfolio) and cash total, this month's income/expenses/net, a 12-month cash-flow chart, spending by category, the three budgets most at risk (over, or ≥75% used), a portfolio card, and upcoming recurring charges |
| **Transactions** (`/transactions`) | Ledger filtered by date range, category, account, or free-text search; sortable and paginated (50 per page, max 500); quick-add form; inline edit and delete; back-dated entries appear immediately |
| **Subscriptions** (`/subscriptions`) | Recurring rules — daily/weekly/monthly/yearly — with next due date, monthly-equivalent cost, and pause/resume |
| **Budgets** (`/budgets`) | Per-category monthly or yearly limits with spent-vs-limit progress; monthly budgets can roll unused amounts forward |
| **Portfolio** (`/portfolio`) | Holdings with live prices, average cost, unrealised gain in EUR, ticker lookup/validation, manual refresh, value history |
| **Reports** (`/reports`) | CSV import with column mapping and preview, CSV export, month-over-month, year-over-year, and yearly comparisons |
| **Settings** (`/settings`) | What's stored, per-category data reset behind two confirmation gates |

Keyboard shortcuts jump between them: `d` dashboard · `t` transactions ·
`s` subscriptions · `b` budgets · `p` portfolio · `r` reports · `g` settings.
Ignored while typing in a field.

## Stack

- **Backend** — Python, FastAPI 0.141 + Uvicorn, SQLAlchemy 2.0 ORM, Alembic
  migrations, Pydantic v2 schemas and settings, APScheduler for the daily jobs,
  yfinance for prices, pytest for tests.
- **Frontend** — React 19 + TypeScript, Vite, React Router 7, Tailwind CSS v4
  (via PostCSS), Recharts, oxlint.
- **Database** — SQLite, one file at `data/finance.db`.
- **Deployment** — none. One Uvicorn process serves the API *and* the built
  frontend as static files, so there is no second server in production.

## Requirements

- Python 3.11+ (developed on 3.14)
- Node 18+ (developed on 24)

## Setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
```

Apply the database schema:

```bash
cd backend
.venv/Scripts/python -m alembic upgrade head
```

Build the frontend:

```bash
cd frontend
npm install
npm run build
```

## Running

**Easiest — double-click `start.bat`** (Windows). It rebuilds the frontend if
its sources changed, launches the server, and opens your browser. Leave the
window open while you use the app; press `Ctrl+C` in it to stop.

**Or by hand** — one process serves both API and UI:

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app
```

- App: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs
- Health/diagnostics: http://127.0.0.1:8000/api/health

**Frontend development** — two processes, with hot reload:

```bash
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload
cd frontend && npm run dev      # http://localhost:5173, proxies /api to :8000
```

Rebuild the frontend (`npm run build`) after changing it, or the backend will
keep serving the previous bundle.

Default categories and a "Main account" are seeded on first startup. The seed
is idempotent, so restarting never duplicates them.

## Project layout

```
backend/
  app/
    main.py          FastAPI app, CORS, SPA static mount, startup/shutdown
    config.py        Pydantic settings (FINANCE_* env vars)
    db.py            engine + SessionLocal
    money.py         cents <-> Decimal helpers, ExactDecimal type
    seed.py          idempotent default categories and account
    api/             one router per resource (see API surface below)
    models/          SQLAlchemy tables: core.py, portfolio.py, base.py (enums)
    services/        business logic: recurring, budgets, portfolio, fx,
                     analytics, reports, csv_io, scheduler, prices/
    schemas/         Pydantic request/response models
  alembic/           migrations
  tests/             pytest suite (171 tests)
frontend/
  src/
    App.tsx          routes, nav, keyboard shortcuts
    theme.ts         chartColors() — chart hues per theme
    index.css        semantic colour tokens + dark override
    api/             typed fetch client (client.ts, types.ts, money.ts)
    components/      QuickAdd, CashFlowChart, SpendingBreakdown, CsvImport, …
    pages/           one per screen
data/                finance.db (gitignored)
```

## API surface

Everything is under `/api`, JSON in and out, no auth (it binds to localhost).
Full schemas are browsable at `/docs`.

| Endpoints | Purpose |
|---|---|
| `GET /api/health` | Liveness, base currency, database path, row counts |
| `GET/POST /api/accounts`, `PATCH/DELETE /api/accounts/{id}` | Accounts |
| `GET/POST /api/categories`, `GET /api/categories/tree`, `PATCH/DELETE /api/categories/{id}` | Categories (nested, income or expense) |
| `GET/POST /api/transactions`, `GET/PATCH/DELETE /api/transactions/{id}` | Ledger; list takes `from`, `to`, `category_id`, `account_id`, `q`, `sort`, `order`, `limit`, `offset` |
| `GET/POST /api/recurring`, `PATCH/DELETE /api/recurring/{id}`, `POST /api/recurring/generate` | Recurring rules; `generate` forces a catch-up run |
| `GET /api/subscriptions` | Recurring rules as a subscription view with monthly cost |
| `GET/POST /api/budgets`, `GET /api/budgets/status`, `PATCH/DELETE /api/budgets/{id}` | Budgets and spent-vs-limit status |
| `GET /api/securities/lookup` | Validate a ticker before saving a holding |
| `GET/POST /api/holdings`, `PATCH/DELETE /api/holdings/{id}` | Holdings |
| `GET /api/portfolio`, `POST /api/portfolio/refresh`, `GET /api/portfolio/history` | Valuation, manual price fetch, value over time |
| `GET /api/dashboard` | Every dashboard widget in one payload |
| `GET /api/reports/export.csv`, `POST /api/reports/columns`, `POST /api/reports/import` | CSV export; column detection; import |
| `GET /api/reports/month-over-month`, `/year-over-year`, `/yearly` | Comparisons |
| `GET /api/settings/data-summary`, `POST /api/settings/reset` | What's stored; scoped delete |

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest
```

171 tests, no network access — the price provider is swapped for
`tests/fake_provider.py` and the database is an in-memory SQLite instance per
test. Frontend checks are `npm run lint` (oxlint) and `npm run build` (which
runs `tsc -b` first).

## Configuration

Settings come from `app/config.py` and can be overridden with environment
variables (or a `.env` file at the repo root) using the `FINANCE_` prefix:

| Variable | Default | Meaning |
|---|---|---|
| `FINANCE_BASE_CURRENCY` | `EUR` | Currency all reporting is done in |
| `FINANCE_DATA_DIR` | `<repo>/data` | Directory holding the database |
| `FINANCE_DB_FILENAME` | `finance.db` | Database file inside the data dir |
| `FINANCE_PRICE_FETCH_HOUR` | `23` | Local hour for the daily price fetch |
| `FINANCE_PRICE_FETCH_MINUTE` | `0` | Minute of that hour |
| `FINANCE_ENABLE_SCHEDULER` | `true` | Background jobs on/off |

The default fetch hour is after the US close so the latest daily close is
actually available.

## Scheduled jobs

APScheduler runs two jobs in-process while the app is open:

- **00:05 daily** — generate recurring transactions that have fallen due. This
  one *also* runs once at startup, so a laptop that was asleep for a week
  catches up on the next launch. Generation is idempotent either way.
- **`FINANCE_PRICE_FETCH_HOUR`:`MINUTE` daily** — fetch share prices and FX
  rates, then write a portfolio snapshot. Not run at startup; use the refresh
  button on the Portfolio page (`POST /api/portfolio/refresh`) to force one.

Both jobs use `misfire_grace_time=None` and `coalesce=True`, so a trigger
missed while the machine was asleep fires once when it wakes rather than being
dropped or replayed N times. A failing job logs and never takes the app down.
Set `FINANCE_ENABLE_SCHEDULER=false` to disable both.

## Backups

Everything lives in `data/finance.db`. Copy that one file to back up, and
close the app first so SQLite isn't mid-write. It is gitignored deliberately —
your financial data should not end up in version control.

## Conventions

- **Money is integer cents in the database and `Decimal` in Python — never
  `float`.** See `app/money.py`.
- **Transaction amounts are signed**: expenses negative, income positive.
- **Share quantities and prices use `ExactDecimal`**, stored as text, because
  SQLAlchemy's `Numeric` passes through float on SQLite.
- **Recurring transactions are real rows**, generated on startup and daily at
  00:05. Generation is idempotent — skipped by due date, and backstopped by a
  `UNIQUE(recurring_rule_id, due_date)` constraint. Editing one month's amount
  is safe and survives regeneration.
- **Recurring dates never drift**: every occurrence is computed from the rule's
  start date, so a rule on the 31st goes Jan 31 → Feb 28 → Mar 31.
- **A failed price fetch never shows zero.** Prices are cached as history, so
  an outage falls back to the last known close and the UI says how old it is.
  All network access sits behind `PriceProvider` (`app/services/prices/`), so
  swapping yfinance for another source is one new class.
- **Average cost is per share, in the security's own currency** (USD for a US
  stock), converted to EUR for the gain figure.

## Adding stock holdings

Tickers use Yahoo symbols. US listings are plain (`AAPL`, `MSFT`); European
ones need an exchange suffix (`SAP.DE`, `ASML.AS`, `MC.PA`). The ticker is
validated before the holding is saved, so a typo fails immediately rather than
becoming a holding that never prices.

## Importing from your bank

Reports → *Import from CSV*. Pick the file, map its columns (common headers in
English and German are detected automatically), then **Preview** before
importing — nothing is written until you confirm.

Handled automatically: comma or semicolon delimiters, `1.234,56` and
`1,234.56` amounts, ISO and day-first dates, trailing-minus negatives, and
UTF-8/Windows-1252 encodings. Categories are matched by name; rows that don't
match fall back to the category you choose. Rows that can't be read are
reported with their line number rather than being silently skipped.

## Dark mode

The toggle sits at the top right: **Light**, **Dark**, or **Match system**
(the default). Your choice is remembered across restarts.

Every colour in the app is a semantic token defined once in
`src/index.css` (`--color-surface`, `--color-ink`, …), so the dark theme is a
single override block rather than per-page styling. The dark values are
*chosen* for the dark surface, not an automatic inversion — the two chart
hues were validated against their own surfaces (colour-blind separation
ΔE 24.7 light / 26.8 dark, against a floor of 8).

Charts are the one exception to the token rule: the charting library writes
colours into SVG attributes, which can't inherit CSS variables, so those are
resolved in JS by `chartColors()` in `src/theme.ts`. Change a chart colour in
both places.

## Resetting data

Settings shows everything currently stored and lets you delete it by
category — transactions, recurring rules, budgets, portfolio, or categories
and accounts. **There is no undo.** Export your transactions first; the button
for it is on the same page.

Two independent gates guard it: you must tick at least one category *and*
type `DELETE MY DATA` exactly. Neither alone does anything, so a stray click
or a mistyped API call deletes nothing.

Clearing categories also clears transactions, rules and budgets, since each
of those points at a category — the default categories and account are
recreated afterwards so the app stays usable.

## Database migrations

After changing a model:

```bash
cd backend
.venv/Scripts/python -m alembic revision --autogenerate -m "what changed"
.venv/Scripts/python -m alembic upgrade head
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| A change to the frontend doesn't appear | The bundle wasn't rebuilt. Run `npm run build` in `frontend/`, or use `start.bat`, which does it for you. |
| Blank page, console 404s on `/assets/…` | No frontend build exists. Same fix. |
| An `/api/…` call returns HTML | It doesn't — unknown `/api/*` paths return a real 404 on purpose. Check the path against `/docs`. |
| Portfolio shows a stale-price note | The last fetch failed; the cached close is shown instead of zero. `POST /api/portfolio/refresh` retries. |
| A new holding is rejected | The ticker failed Yahoo lookup. European listings need the exchange suffix (`SAP.DE`). |
| `no such table` on startup | Migrations weren't applied: `alembic upgrade head`. |

## Project status

- [x] Phase 1 — Foundation: models, migrations, seed, health endpoint
- [x] Phase 2 — Cash flow core: transaction/category/account API, React UI
- [x] Phase 3 — Recurring & subscriptions: rules, generator, scheduler, UI
- [x] Phase 4 — Budgets: limits, status, rollover, progress UI
- [x] Phase 5 — Portfolio: live prices, FX, holdings, stale fallback
- [x] Phase 6 — Dashboard: KPIs, cash-flow chart, spending, budgets, portfolio
- [x] Phase 7 — Reports & polish: CSV import/export, comparisons, shortcuts

All seven phases of [PRD.md](PRD.md) are complete. 171 tests pass.
