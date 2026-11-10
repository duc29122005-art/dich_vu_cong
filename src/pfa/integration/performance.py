"""Separately invoked small synthetic timings, without production performance promises."""

import os
import platform
from statistics import median
from time import perf_counter

from sqlalchemy import func, select

from pfa.analytics.fixtures import seed
from pfa.db.models import Feedback
from pfa.db.smoke import environment


def measure(operation, samples=20, *, items=1):
    durations = []
    for _ in range(samples):
        started = perf_counter()
        operation()
        durations.append(perf_counter() - started)
    ordered = sorted(durations)
    return {
        "samples": samples,
        "items_per_sample": items,
        "median_ms": median(durations) * 1000,
        "p95_ms": ordered[int(0.95 * (samples - 1))] * 1000,
        "items_per_second": samples * items / sum(durations),
    }


def smoke(root):
    with environment(root) as (client, database, headers, temporary):
        (temporary / "configs/analytics_v1.yaml").write_bytes(
            (root / "configs/analytics_v1.yaml").read_bytes()
        )
        seed(database)
        auth = headers["ADMIN"]
        body = {"text": "SYNTHETIC: Thủ tục giả lập cần hướng dẫn rõ ràng."}

        def request(method, path, **options):
            response = client.request(method, path, headers=auth, **options)
            assert response.status_code == 200

        def query():
            with database.sessions() as session:
                assert session.scalar(select(func.count()).select_from(Feedback)) == 420

        result = {
            "single_prediction": measure(lambda: request("POST", "/api/v1/predict", json=body)),
            "batch_prediction": measure(
                lambda: request("POST", "/api/v1/predict/batch", json={"items": [body] * 8}),
                items=8,
            ),
            "database_query": measure(query),
            "review_queue": measure(lambda: request("GET", "/api/v1/reviews/queue")),
            "analytics": measure(lambda: request("GET", "/api/v1/analytics/summary")),
        }
    return {
        "status": "PERFORMANCE_SMOKE_PASS_SYNTHETIC",
        "processing_mode": "DEMO_ONLY",
        "backend": "SQLite",
        "transport": "IN_PROCESS_TESTCLIENT",
        "seed_records": 420,
        "python": platform.python_version(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "measurements": result,
        "temporary_storage_cleaned": not temporary.exists(),
        "limitation": "Local sequential synthetic timings; not network or production capacity",
    }
