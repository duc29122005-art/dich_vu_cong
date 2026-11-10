"""Temporary invented corpus and predetermined labels; never human research gold."""

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot_store as store
from pfa.annotation.agreement import TASKS
from pfa.annotation.taxonomy import CHECKSUM
from pfa.data import corpus, official
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.profiling import SYNTHETIC_KEY
from pfa.data.registry import Registry
from pfa.data.splitting import CorpusRow, SplitConfig, group_rows


def fixture(n: int = 120) -> tuple[list[CorpusRow], dict]:
    """Invented text with known exact duplicates, relations, and unknown severity."""
    rng = random.Random(8)
    words = (
        "thủ tục hướng dẫn chưa không hài lòng tiếp nhận trực tuyến lịch hẹn "
        "kết quả xử lý nhanh rõ ràng phí dịch vụ hỗ trợ phản hồi"
    ).split()
    values = []
    for i in range(n):
        labels = {task: codes[i % len(codes)] for task, codes in TASKS.items()}
        if i % 19 == 0:
            labels["severity"] = None
        values.append(
            CorpusRow(
                feedback_id="f_" + f"{i:032x}",
                content="SYNTHETIC: " + " ".join(rng.sample(words, 12)) + f" mục {i}.",
                source_id="synthetic_demo",
                source_version="synthetic_corpus_1",
                taxonomy_checksum=CHECKSUM,
                dataset_type="SYNTHETIC",
                event_time=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i),
                group_id=f"synthetic_group_{i // 2}",
                relations=[],
                labels=labels,
                eligible={task: value is not None for task, value in labels.items()},
                exclusion_reasons={
                    task: "UNKNOWN_SEVERITY_SYNTHETIC" if value is None else None
                    for task, value in labels.items()
                },
                holdout_eligible=True,
                domain_bucket=None,
                agency_bucket=None,
            )
        )
    if n >= 4:
        values[1].content = values[0].content
        relation = "case:" + "a" * 64
        values[2].relations = [relation]
        values[3].relations = [relation]

    def fp(value: str) -> str:
        return official.fingerprint(SYNTHETIC_KEY, "corpus-lineage-1", value)

    grouped = group_rows(values, fp) if values else []
    provenance = {
        "dataset_type": "SYNTHETIC",
        "human_gold": False,
        "source_id": "synthetic_demo",
        "source_version": "synthetic_corpus_1",
        "source_manifest_checksum": store.digest([row.model_dump(mode="json") for row in values]),
        "source_record_count": n,
        "annotated_count": n,
        "excluded_records": {},
        "unannotated_source_count": 0,
        "gold_revisions": {},
        "usage": "PREDETERMINED_SOFTWARE_FIXTURE_ONLY",
    }
    return grouped, provenance


def smoke(registry: Registry) -> dict:
    with TemporaryDirectory(prefix="pfa-split-synthetic-") as temporary:
        root = Path(temporary)
        with store.synthetic_session(root):
            records, provenance = fixture()
            result = corpus._publish(
                root, "synthetic_split_v1", records, provenance, SplitConfig(), 42
            )
            verification = corpus.verify(root, registry, "synthetic_split_v1")
            for split in ("train", "validation"):
                actual = corpus.model_selection(root, registry, "synthetic_split_v1", split)
                if len(actual) != result["report"]["counts"][split]:
                    raise IngestionError("Synthetic development membership check failed")
            try:
                corpus.model_selection(root, registry, "synthetic_split_v1", "test")
            except IngestionBlocked:
                pass
            else:
                raise IngestionError("Synthetic holdout restriction failed")
            if verification["leakage"]["critical_count"]:
                raise IngestionError("Synthetic leakage validation failed")
            summary = {
                "status": "SPLIT_SMOKE_PASS_SYNTHETIC",
                "dataset_type": "SYNTHETIC",
                "human_gold": False,
                "record_count": len(records),
                "counts": result["report"]["counts"],
                "ratios": result["report"]["ratios"],
                "warnings": result["report"]["warnings"],
                "leakage": verification["leakage"],
                "task_exclusions": result["report"]["task_exclusions"],
                "test_access_blocked": True,
                "checksums_verified": True,
            }
    summary["temporary_storage_cleaned"] = not root.exists()
    return summary
