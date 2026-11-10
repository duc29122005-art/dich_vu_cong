"""Local calendar buckets using event timestamps only, never insertion timestamps."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pfa.analytics.kpis import labels, metric
from pfa.analytics.schemas import Bucket

ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def local_date(row):
    if row.event_time is None:
        return None
    if row.event_time.tzinfo is None or row.event_time.utcoffset() is None:
        raise ValueError("Verified aware event timestamps required")
    return row.event_time.astimezone(ZONE).date()


def start_of(day, interval):
    return (
        day - timedelta(days=day.weekday())
        if interval == "week"
        else day.replace(day=1)
        if interval == "month"
        else day
    )


def next_bucket(day, interval):
    if interval != "month":
        return day + timedelta(days=7 if interval == "week" else 1)
    return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)


def group(rows, filters, config, *, today=None):
    dated = [(local_date(row), row) for row in rows if row.event_time is not None]
    start = filters.start or (min(d for d, _ in dated) if dated else None)
    end = filters.end or (max(d for d, _ in dated) if dated else None)
    if start is None:
        return [], []
    if (end - start).days >= config.max_days:
        raise ValueError("Explicit bounded reporting window required")
    grouped = defaultdict(list)
    for day, row in dated:
        if start <= day <= end:
            grouped[start_of(day, filters.interval)].append(row)
    buckets, members = [], []
    day = start_of(start, filters.interval)
    today = today or datetime.now(UTC).astimezone(ZONE).date()
    while day <= end:
        following = next_bucket(day, filters.interval)
        records = grouped[day]
        chosen = [labels(r, filters.basis) for r in records]
        negative = sum(v.get("sentiment") == "negative" for v in chosen)
        sentiments = sum(v.get("sentiment") in {"negative", "neutral", "positive"} for v in chosen)
        high = sum(v.get("severity") == "high" for v in chosen)
        severity = sum(v.get("severity") in {"low", "medium", "high"} for v in chosen)
        suppressed = 0 < len(records) < config.small_group
        negative_metric = metric(negative, sentiments, config.small_group)
        high_metric = metric(high, severity, config.small_group)
        for value, known in ((negative_metric, sentiments), (high_metric, severity)):
            if metric(known, len(records), config.small_group).suppressed:
                value.numerator = value.denominator = value.share = None
                value.suppressed = True
        buckets.append(
            Bucket(
                start=day,
                end_exclusive=following,
                count=None if suppressed else len(records),
                suppressed=suppressed,
                negative=negative_metric,
                high_severity=high_metric,
                complete_calendar_window=day >= start
                and following <= end + timedelta(days=1)
                and following <= today,
            )
        )
        members.append(records)
        day = following
    return buckets, members
