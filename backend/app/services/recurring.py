"""Turning recurring rules into real transactions.

Two properties matter more than anything else here:

1. **Idempotency.** Generation runs on every startup *and* on a daily
   schedule, so the same due date will be considered many times. It must never
   produce a second charge. Enforced twice: we skip due dates that already
   have a transaction, and the database has a UNIQUE(recurring_rule_id,
   due_date) constraint as a backstop.

2. **No month-end drift.** Every occurrence is computed from the rule's
   original start date, never from the previous occurrence. A rule on the 31st
   must go Jan 31 -> Feb 28 -> Mar 31, not Jan 31 -> Feb 28 -> Mar 28. Deriving
   each date from the last one accumulates exactly that error.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Frequency, RecurringRule, Transaction

logger = logging.getLogger(__name__)

# A safety valve: if a rule's start date is far in the past, generating every
# occurrence could create thousands of rows. Daily rules over a decade would.
MAX_OCCURRENCES = 1000


def add_months(anchor: date, months: int, day: int | None = None) -> date:
    """Shift by whole months, clamping the day to the target month's length.

    `day` defaults to the anchor's day. Day 31 in a 30-day month becomes the
    30th, and in February the 28th or 29th.
    """
    target_day = day if day is not None else anchor.day
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(target_day, last_day))


def occurrences(rule: RecurringRule, until: date) -> list[date]:
    """Every due date from the rule's start through `until`, inclusive."""
    if rule.interval < 1:
        raise ValueError("interval must be at least 1")

    end = min(until, rule.end_date) if rule.end_date else until
    if end < rule.start_date:
        return []

    start = rule.start_date
    result: list[date] = []

    if rule.frequency == Frequency.daily:
        step = timedelta(days=rule.interval)
        current = start
        while current <= end and len(result) < MAX_OCCURRENCES:
            result.append(current)
            current += step

    elif rule.frequency == Frequency.weekly:
        # If a weekday is specified, the series starts on the first such day on
        # or after the start date, so a rule created mid-week still lands right.
        current = start
        if rule.weekday is not None:
            offset = (rule.weekday - start.weekday()) % 7
            current = start + timedelta(days=offset)
        step = timedelta(weeks=rule.interval)
        while current <= end and len(result) < MAX_OCCURRENCES:
            result.append(current)
            current += step

    else:
        months_per_step = {
            Frequency.monthly: 1,
            Frequency.quarterly: 3,
            Frequency.yearly: 12,
        }[rule.frequency] * rule.interval

        day = rule.day_of_month or start.day
        # The first occurrence may fall before the start date once the day is
        # applied (rule starts on the 15th but bills on the 1st) — in that case
        # the series begins the following period.
        n = 0
        first = add_months(start, 0, day)
        if first < start:
            n = 1

        while len(result) < MAX_OCCURRENCES:
            current = add_months(start, n * months_per_step, day)
            if current > end:
                break
            result.append(current)
            n += 1

    return result


@dataclass
class GenerationResult:
    created: int
    rules_processed: int

    def __bool__(self) -> bool:
        return self.created > 0


def generate_for_rule(session: Session, rule: RecurringRule, until: date) -> int:
    """Materialize any missing transactions for one rule. Returns count created."""
    if not rule.active:
        return 0

    due_dates = occurrences(rule, until)
    if not due_dates:
        return 0

    existing = set(
        session.scalars(
            select(Transaction.due_date).where(
                Transaction.recurring_rule_id == rule.id
            )
        )
    )

    created = 0
    for due in due_dates:
        if due in existing:
            continue
        session.add(
            Transaction(
                date=due,
                due_date=due,
                amount_cents=rule.amount_cents,
                account_id=rule.account_id,
                category_id=rule.category_id,
                description=rule.description or rule.name,
                recurring_rule_id=rule.id,
            )
        )
        created += 1

    if created:
        rule.last_generated_date = due_dates[-1]

    return created


def generate_due_transactions(
    session: Session, until: date | None = None
) -> GenerationResult:
    """Materialize every active rule's due transactions up to `until` (today)."""
    until = until or date.today()

    rules = list(session.scalars(select(RecurringRule).where(RecurringRule.active)))
    total = 0
    for rule in rules:
        total += generate_for_rule(session, rule, until)

    if total:
        session.commit()
        logger.info("Generated %s recurring transaction(s)", total)
    else:
        # Nothing to write, but rules may have been loaded into the session.
        session.rollback()

    return GenerationResult(created=total, rules_processed=len(rules))


def next_due_date(rule: RecurringRule, after: date | None = None) -> date | None:
    """The next occurrence strictly after `after` (default today)."""
    after = after or date.today()
    if not rule.active:
        return None

    # Look ahead far enough to cover a yearly rule with a large interval.
    horizon = add_months(after, 12 * max(rule.interval, 1) + 12)
    if rule.end_date and rule.end_date < horizon:
        horizon = rule.end_date

    for due in occurrences(rule, horizon):
        if due > after:
            return due
    return None


# Periods per year, used to express any frequency as a monthly cost.
PERIODS_PER_YEAR = {
    Frequency.daily: 365,
    Frequency.weekly: 52,
    Frequency.monthly: 12,
    Frequency.quarterly: 4,
    Frequency.yearly: 1,
}


def monthly_equivalent_cents(rule: RecurringRule) -> int:
    """What this rule costs per month on average.

    Lets a yearly insurance premium and a monthly streaming plan be compared
    and summed in one column.
    """
    per_year = PERIODS_PER_YEAR[rule.frequency] / rule.interval
    return round(abs(rule.amount_cents) * per_year / 12)
