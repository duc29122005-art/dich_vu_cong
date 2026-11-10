"""Apply explicit label/time filters and suppression before aggregate serialization."""

from collections import Counter

from fastapi import HTTPException

from pfa.analytics import alerts, kpis, repository, trends
from pfa.analytics.schemas import ModelInfo, Report
from pfa.annotation import pilot_store as store


def build(repo, filters, config, endpoint):
    if filters.start and (filters.end - filters.start).days >= config.max_days:
        raise HTTPException(422, "BOUNDED_REPORTING_WINDOW_REQUIRED")
    if (
        filters.agency
        and filters.agency not in config.agencies
        or filters.domain
        and filters.domain not in config.domains
    ):
        raise HTTPException(422, "UNSUPPORTED_METADATA_FILTER")
    rows = repository.read(repo, filters, config)
    models = sorted({(task, *model) for row in rows for task, model in row.models.items()})
    if filters.model_version and filters.model_version not in {model[2] for model in models}:
        raise HTTPException(422, "UNSUPPORTED_MODEL_VERSION")
    chosen = []
    for row in rows:
        values = kpis.labels(row, filters.basis)
        model = row.models.get(filters.model_task)
        if (
            (filters.agency and row.agency != filters.agency)
            or (filters.domain and row.domain != filters.domain)
            or (filters.review_status and row.state != filters.review_status)
            or any(
                getattr(filters, task) and values.get(task) != getattr(filters, task)
                for task in kpis.LABELS
            )
            or (filters.model_family and (model is None or model[0] != filters.model_family))
            or (filters.model_version and (model is None or model[1] != filters.model_version))
        ):
            continue
        chosen.append(row)
    missing_dates = sum(r.event_time is None for r in chosen)
    missing_share = missing_dates / len(chosen) if chosen else None
    if filters.start:
        records = [
            r
            for r in chosen
            if r.event_time is not None and filters.start <= trends.local_date(r) <= filters.end
        ]
    else:
        records = chosen
    n = len(records)
    suppressed = 0 < n < config.small_group
    report = Report(
        config_checksum=store.digest(config.model_dump()),
        filters=filters,
        total=None if suppressed else n,
        small_group=config.small_group,
        status="SUPPRESSED" if suppressed else "AVAILABLE" if n else "EMPTY",
    )
    if suppressed:
        report.warnings.append("ENTIRE_SMALL_COHORT_SUPPRESSED")
        return report
    report.metrics["missing_event_time_in_filter_scope"] = kpis.metric(
        missing_dates, len(chosen), config.small_group
    )
    if endpoint == "summary":
        metrics, distributions, top, cross = kpis.summarize(
            records, filters.basis, config.small_group
        )
        report.metrics.update(metrics)
        for dimension, approved in (("agency", config.agencies), ("domain", config.domains)):
            report.metrics[dimension + "_missing"] = kpis.metric(
                sum(getattr(r, dimension) is None for r in records), n, config.small_group
            )
            report.metrics[dimension + "_unapproved"] = kpis.metric(
                sum(
                    getattr(r, dimension) is not None and getattr(r, dimension) not in approved
                    for r in records
                ),
                n,
                config.small_group,
            )
        report.distributions = distributions
        report.top_complaint_topic = top
        report.cross_tab = cross
        visible_models = sorted(
            {(task, *model) for row in records for task, model in row.models.items()}
        )
        report.models = [
            ModelInfo(task=task, family=family, version=version, status="DEMO_ONLY")
            for task, family, version in visible_models
        ]
    elif endpoint == "topics":
        _, distributions, _, _ = kpis.summarize(records, filters.basis, config.small_group)
        report.distributions["topic"] = distributions["topic"]
        for dimension, approved in (("agency", config.agencies), ("domain", config.domains)):
            counts = Counter(
                getattr(r, dimension)
                if getattr(r, dimension) in approved
                else "missing"
                if getattr(r, dimension) is None
                else "unapproved_metadata"
                for r in records
            )
            report.distributions[dimension] = kpis.cells(
                counts, [*approved, "missing", "unapproved_metadata"], config.small_group
            )
    else:
        try:
            buckets, members = trends.group(records, filters, config)
        except ValueError:
            raise HTTPException(422, "BOUNDED_REPORTING_WINDOW_REQUIRED") from None
        if endpoint == "trends":
            # Suppress the whole series if one nonzero time cell is small: no residual subtraction.
            if any(b.suppressed for b in buckets):
                report.warnings.append("TIME_SERIES_SMALL_CELL_SUPPRESSED")
                for bucket in buckets:
                    bucket.count, bucket.suppressed = None, True
                    for metric in (bucket.negative, bucket.high_severity):
                        metric.numerator = metric.denominator = metric.share = None
                        metric.suppressed = True
            report.buckets = buckets
        else:
            report.alerts = alerts.evaluate(buckets, members, filters, config, missing_share)
            for alert in report.alerts:
                if buckets:
                    alert.window_start = buckets[-1].start
                    alert.window_end_exclusive = buckets[-1].end_exclusive
                if len(buckets) > config.baseline_windows:
                    alert.baseline_start = buckets[-config.baseline_windows - 1].start
                    alert.baseline_end_exclusive = buckets[-1].start
            report.warnings.append("RETROSPECTIVE_INDICATORS_FOR_REQUESTED_WINDOW")
    return report
