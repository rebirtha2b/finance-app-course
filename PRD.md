# PRD — Personal Finance & Portfolio Tracker

## Context

You want one place to see your complete financial picture, replacing whatever
mix of spreadsheets and bank apps you use today. Two halves that most tools
keep separate:

1. **Cash flow** — income and expenses, entered manually. Recurring costs
   (rent, subscriptions, insurance) are the part spreadsheets handle worst,
   because they must be re-typed every month and are easy to forget.
2. **Portfolio** — stock holdings entered as share counts, valued
   automatically against the latest daily closing price so you never look up
   quotes by hand.

The intended outcome: open one page and immediately answer "how much did I
spend this month, on what, am I over budget, and what is my portfolio worth
right now?"

**Scope note:** everything is manual entry. No bank connections, no broker
sync, no tax reporting. This keeps the build tractable and avoids the
credential/regulatory surface of open banking APIs.

---

## 1. Product summary

| | |
|---|---|
| **Name** | finance_app (working title) |
| **Users** | One person (you). Single-user, no accounts, no login. |
| **Form factor** | Local web app — runs on your machine, opened at `http://localhost:8000` |
| **Base currency** | EUR. USD-denominated holdings converted via daily FX rate. |
| **Data** | Local SQLite file. No cloud, no third party sees your finances. |

### Success criteria

- Logging an expense takes under 10 seconds.
- Recurring items (rent, Netflix, gym) are entered **once** and appear
  automatically each period.
- Portfolio value is current to the last market close without any manual
  price entry.
- The dashboard answers the four core questions above without navigation.

---

## 2. Domain model

```
Account        id, name, type(cash|bank|broker), currency, opening_balance
Category       id, name, kind(income|expense), parent_id, icon, color, archived
Transaction    id, date, amount(EUR, signed), currency, fx_rate, account_id,
               category_id, description, notes, recurring_rule_id?, created_at
RecurringRule  id, template(amount, category, description, account),
               frequency(daily|weekly|monthly|quarterly|yearly), interval,
               day_of_month|weekday, start_date, end_date?, active,
               last_generated_date
Budget         id, category_id, period(monthly|yearly), limit_amount,
               start_month, active
Security       id, ticker, name, exchange, currency, asset_type
Holding        id, security_id, account_id, quantity, avg_cost_price?, notes
PriceSnapshot  id, security_id, date, close_price, currency, fetched_at
FxRate         id, base, quote, date, rate
PortfolioSnapshot  id, date, total_value_eur, total_cost_eur   (daily, for history chart)
```

**Design decisions:**

- **Amounts stored as integer minor units** (cents) — never floats. Money
  arithmetic with `float` produces rounding drift that surfaces as €0.01
  discrepancies in totals.
- **Signed amounts on transactions**: expenses negative, income positive.
  `kind` on the category is the classification; the sign is the arithmetic.
  Avoids a whole class of "did I remember to negate this" bugs.
- **`PriceSnapshot` is a cache with history**, not just a latest-value field.
  Storing every fetched close gives the portfolio-over-time chart for free
  and means a failed API call falls back to the last known price rather than
  showing €0.
- **Transactions generated from a `RecurringRule` are real rows**, materialized
  on a schedule, not computed on the fly. This lets you edit a single month's
  rent (it went up) without breaking the rule, and keeps every report a plain
  query over `Transaction`.

---

## 3. Features

### 3.1 Income & expense tracking (P0)

- Quick-add form: amount, date (defaults today), category, account,
  description. Keyboard-first — the amount field is focused on load, Enter
  submits.
- Full transaction list with filters: date range, category, account,
  free-text search on description. Sortable, paginated.
- Inline edit and delete with undo.
- Split transactions (one purchase across multiple categories) — P2.

### 3.2 Categories (P0)

Seeded on first run so the app is usable immediately, all editable:

**Expenses** — Housing (Rent, Utilities, Internet, Maintenance) · Food
(Groceries, Restaurants, Delivery) · Transport (Fuel, Public transit, Car
insurance, Repairs) · Subscriptions (Streaming, Software, Cloud storage,
Gym, Phone) · Health (Insurance, Pharmacy, Doctor) · Shopping (Clothing,
Electronics, Household) · Entertainment · Travel · Education · Gifts &
donations · Fees & interest · Taxes · Other

**Income** — Salary · Bonus · Freelance · Dividends · Interest · Refunds ·
Rental income · Other

Two levels only (parent → child). Deeper trees complicate every rollup query
and nobody uses them.

### 3.3 Recurring items & subscriptions (P0)

The headline feature for subscriptions.

- Define a rule: amount, category, frequency, day of month, start/end date.
- A generator runs on app startup and once daily, materializing any due
  transactions up to today. Idempotent — keyed on
  `(rule_id, due_date)` so a double run cannot duplicate a charge.
- **Subscriptions view**: every active recurring expense, its monthly-
  equivalent cost, next charge date, and a total annualized subscription
  spend. This is the number that makes people cancel things.
- Pause / resume / end a rule without deleting its history.
- Optional price-change log: amend a rule's amount and record when it changed.

### 3.4 Budgets (P0)

- Monthly limit per category (or per parent category, covering its children).
- Progress bars: spent / limit, with over-budget highlighted.
- Roll-over toggle — unspent budget carries to next month (P1).
- Dashboard surfaces the top 3 categories closest to or over limit.

### 3.5 Portfolio tracking (P0)

- Add holding: ticker, number of shares, optional average cost, account.
- Ticker lookup validates the symbol against the price provider and stores
  the resolved name, exchange, and native currency before saving. Prevents
  silent typos from creating a holding that will never price.
- Fractional shares supported (store quantity as `Decimal`).
- Per-holding row: shares, last close, native value, EUR value, day change,
  total gain/loss vs. cost basis, % of portfolio.
- Portfolio total in EUR, plus allocation donut by holding and by currency.
- Portfolio value over time, from `PortfolioSnapshot`.
- Manual "Refresh prices" button in addition to the scheduled fetch.

### 3.6 Price & FX data (P0)

- **Provider: `yfinance`** — free, no API key, covers US and European
  exchanges (`AAPL`, `SAP.DE`, `ASML.AS`).
- Fetch the **latest daily close** for all held tickers, batched in a single
  request, once daily after US market close plus on demand.
- FX: EUR/USD (and other needed pairs) daily rate from the same source
  (`EURUSD=X`), cached in `FxRate`.
- **Failure handling is a requirement, not a nicety.** `yfinance` scrapes an
  unofficial endpoint and does break. On failure: keep the last good price,
  show a visible "prices as of <date>" staleness indicator, log the error,
  never display €0 or crash the dashboard.
- All provider access sits behind a `PriceProvider` interface with
  `get_latest_close(tickers)` and `get_fx_rate(base, quote)`, so swapping in
  Alpha Vantage or Finnhub later is one new class, not a refactor.

### 3.7 Dashboard (P0)

Single landing page:

- **Top row**: net worth (cash balances + portfolio), this month's income,
  this month's expenses, this month's net.
- **Cash flow chart**: income vs. expenses by month, last 12 months.
- **Spending breakdown**: current month by category (donut + ranked list).
- **Budget status**: categories at risk or over.
- **Portfolio card**: total value, day change, top movers.
- **Upcoming**: recurring charges due in the next 14 days.

### 3.8 Reports (P1)

- Month-over-month and year-over-year category comparison.
- Yearly summary: total income, expenses, savings rate.
- CSV export of transactions; CSV import with column mapping.

---

## 4. Technical design

**Stack**

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI | Same language as `yfinance` and pandas; auto-generated API docs |
| DB | SQLite via SQLAlchemy 2.x | Single file, zero setup, correct for one user |
| Migrations | Alembic | Schema will change; hand-editing SQLite is misery |
| Frontend | React + Vite + TypeScript | Interactive dashboard with filters |
| Styling | Tailwind CSS | Fast, consistent |
| Charts | Recharts | Composes cleanly with React |
| Scheduling | APScheduler in-process | Daily price fetch + recurring generation, no external cron |
| Money | `Decimal` in Python, integer cents in DB | No float drift |
| Tests | pytest + httpx | |

**Deployment shape:** FastAPI serves the built React bundle as static files,
so running the app is one command (`uvicorn app.main:app`) hitting one port.
A dev script runs Vite's dev server with a proxy for hot reload.

**Layout**

```
finance_app/
  backend/
    app/
      main.py               FastAPI app, static mount, scheduler startup
      config.py             settings (base currency, DB path, fetch time)
      db.py                 engine, session
      models/               SQLAlchemy models
      schemas/              Pydantic request/response
      api/                  transactions, categories, recurring, budgets,
                            holdings, dashboard, reports
      services/
        recurring.py        rule → transaction materialization
        portfolio.py        valuation, gain/loss, allocation
        prices/
          base.py           PriceProvider interface
          yfinance_provider.py
        fx.py               currency conversion
        analytics.py        aggregations for dashboard/reports
      seed.py               default categories
    alembic/
    tests/
  frontend/
    src/
      pages/       Dashboard, Transactions, Subscriptions, Budgets, Portfolio, Settings
      components/  forms, tables, charts, layout
      api/         typed client
  data/finance.db             (gitignored)
  README.md
```

**API sketch**

```
GET/POST/PATCH/DELETE  /api/transactions        filters: from,to,category,account,q
GET/POST/PATCH/DELETE  /api/categories
GET/POST/PATCH/DELETE  /api/recurring           + POST /api/recurring/generate
GET                    /api/subscriptions       active recurring expenses + annualized
GET/POST/PATCH/DELETE  /api/budgets
GET                    /api/budgets/status      spent vs limit, current month
GET/POST/PATCH/DELETE  /api/holdings
GET                    /api/portfolio           valued holdings + totals
POST                   /api/portfolio/refresh   force price fetch
GET                    /api/portfolio/history   snapshots for chart
GET                    /api/securities/search   ticker validation/lookup
GET                    /api/dashboard           one call, everything above the fold
GET                    /api/reports/...
```

---

## 5. Build order

**Phase 1 — Foundation**
Project scaffold, SQLAlchemy models, Alembic baseline, category seed, health
endpoint. Verify: `uvicorn` starts, `/docs` lists routes, DB file created
with seeded categories.

**Phase 2 — Cash flow core**
Transaction + category CRUD, React shell with routing, quick-add form,
transaction table with filters. Verify: add/edit/delete income and expenses,
filters return correct rows.

**Phase 3 — Recurring & subscriptions**
`RecurringRule` CRUD, idempotent generator service, APScheduler daily job,
subscriptions view with annualized total. Verify: create a monthly rule
starting three months ago → generator creates exactly 3 transactions;
running it twice creates no duplicates.

**Phase 4 — Budgets**
Budget CRUD, status endpoint, progress UI. Verify: budget of €400 with €450
spent shows over-budget.

**Phase 5 — Portfolio**
`PriceProvider` + yfinance implementation, FX, holdings CRUD with ticker
validation, valuation service, portfolio page. Verify: add 10 `AAPL` and 5
`SAP.DE`, values match the previous close converted to EUR; disconnect the
network → last known prices shown with a staleness banner.

**Phase 6 — Dashboard**
Aggregation endpoint, KPI tiles, charts, upcoming charges, portfolio card.
Verify: numbers reconcile with the transactions and portfolio pages.

**Phase 7 — Reports & polish**
CSV export/import, comparison reports, empty states, keyboard shortcuts,
README with setup instructions.

---

## 6. Verification

**Automated (pytest)**
- Recurring generation: idempotency, catch-up from a past start date,
  month-end edge cases (a rule on the 31st in February).
- Money arithmetic: no float drift across 1000 summed transactions.
- FX conversion: USD holding → EUR at a known fixed rate.
- Price provider: mocked success, timeout, and malformed-response paths;
  stale-fallback behavior.
- Budget status boundaries: exactly at limit, over, no spending.
- API contract tests per router.

**Manual end-to-end**
1. Fresh start → seeded categories present.
2. Enter a month of realistic income and expenses.
3. Create rent + three subscription rules → verify generated charges and the
   annualized subscription total.
4. Set budgets, exceed one, confirm dashboard flags it.
5. Add three holdings across EUR and USD → refresh prices → cross-check two
   tickers against a public quote source.
6. Kill network, reload → app renders with a staleness indicator, no crash.
7. Restart the app → all data persists, no duplicate recurring transactions.

---

## 7. Explicitly out of scope

Bank/broker API connections · multi-user accounts and auth · mobile native
apps · tax reporting · crypto (P3) · options and bonds · intraday prices ·
receipt OCR · cloud sync

---

## 8. Open questions

- Do you want **cost basis and realized gains** (requires logging buy/sell
  transactions with dates), or is current value plus a manually entered
  average cost enough? The PRD assumes the simpler version.
- Should dividends received automatically create an income transaction, or
  will you enter those manually?
- Preferred daily price-fetch time (default: 23:00 local, after US close).
