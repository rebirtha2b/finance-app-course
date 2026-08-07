# Finance App

Personal income, expense, and stock portfolio tracker. Runs locally, stores
everything in a single SQLite file, and never sends your financial data
anywhere. See [PRD.md](PRD.md) for the full specification.

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

**Easiest — double-click `start.bat`** (Windows). It launches the server and
opens your browser. Leave the window open while you use the app; press
`Ctrl+C` in it to stop.

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

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest
```

## Configuration

Settings come from `app/config.py` and can be overridden with environment
variables (or a `.env` file at the repo root) using the `FINANCE_` prefix:

| Variable | Default | Meaning |
|---|---|---|
| `FINANCE_BASE_CURRENCY` | `EUR` | Currency all reporting is done in |
| `FINANCE_PRICE_FETCH_HOUR` | `23` | Local hour for the daily price fetch |
| `FINANCE_ENABLE_SCHEDULER` | `true` | Background jobs on/off |
| `FINANCE_DB_FILENAME` | `finance.db` | Database file inside `data/` |

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

## Keyboard shortcuts

`d` dashboard · `t` transactions · `s` subscriptions · `b` budgets ·
`p` portfolio · `r` reports · `g` settings. Ignored while typing in a field.

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

## Project status

- [x] Phase 1 — Foundation: models, migrations, seed, health endpoint
- [x] Phase 2 — Cash flow core: transaction/category/account API, React UI
- [x] Phase 3 — Recurring & subscriptions: rules, generator, scheduler, UI
- [x] Phase 4 — Budgets: limits, status, rollover, progress UI
- [x] Phase 5 — Portfolio: live prices, FX, holdings, stale fallback
- [x] Phase 6 — Dashboard: KPIs, cash-flow chart, spending, budgets, portfolio
- [x] Phase 7 — Reports & polish: CSV import/export, comparisons, shortcuts

All seven phases of [PRD.md](PRD.md) are complete. 160 tests pass.
