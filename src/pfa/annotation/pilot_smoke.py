"""Eight invented Vietnamese records and predetermined software labels; no human research."""

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot
from pfa.annotation import pilot_store as store
from pfa.annotation.io import COLUMNS, metadata_path
from pfa.annotation.schema import BlankAnnotation
from pfa.annotation.taxonomy import CHECKSUM, VERSION, load_taxonomy
from pfa.data import official
from pfa.data.official_io import protect_directory, write_json
from pfa.data.official_schema import Feedback
from pfa.data.profiling import SYNTHETIC_KEY
from pfa.data.registry import Registry


def create_synthetic(root: Path, project_root: Path, n: int = 8) -> pilot.PilotManifest:
    """Only callable inside the temporary in-process synthetic capability."""
    store.require_synthetic(root)
    load_taxonomy(project_root)
    (root / "configs").mkdir(exist_ok=True)
    (root / "configs/taxonomy_v1.yaml").write_bytes(
        (project_root / "configs/taxonomy_v1.yaml").read_bytes()
    )
    now = datetime.now(UTC)
    plan = pilot.PilotPlan(
        plan_ref="synthetic_software_plan",
        dataset_type="SYNTHETIC",
        source_id="synthetic_demo",
        dataset_version="of_" + "7" * 32,
        target_count=n,
        seed=42,
        coordinator_sid="S-1-5-21-1000",
        annotators={
            "A": pilot.Actor(annotator_id="ann_" + "a" * 16, windows_sid="S-1-5-21-1001"),
            "B": pilot.Actor(annotator_id="ann_" + "b" * 16, windows_sid="S-1-5-21-1002"),
        },
        adjudicator=pilot.Actor(annotator_id="ann_" + "c" * 16, windows_sid="S-1-5-21-1003"),
        submission_deadline=(now + timedelta(days=1)).isoformat(),
        reviewer_id="synthetic_simulation_only",
        evidence_reference="synthetic_no_human_evidence",
        reviewed_at=now.isoformat(),
        human_verified=False,
    )
    records = [
        Feedback(
            feedback_id="f_" + official.fingerprint(SYNTHETIC_KEY, "pilot-smoke", str(i))[:32],
            content=f"SYNTHETIC: Thủ tục giả lập mục {i} chưa có hướng dẫn rõ ràng.",
            created_at=None,
            source_id="synthetic_demo",
            domain=None,
        )
        for i in range(n)
    ]
    return pilot._create(
        root,
        "pilot_synthetic",
        plan,
        records,
        SYNTHETIC_KEY,
        store.digest([item.model_dump(mode="json") for item in records]),
        None,
        {"dataset_type": "SYNTHETIC", "usage": "SOFTWARE_TEST_ONLY"},
        {},
    )


def synthetic_submission(
    root: Path,
    registry: Registry,
    manifest: pilot.PilotManifest,
    actor: str,
    *,
    revision: int = 1,
    modifications: dict[int, dict] | None = None,
) -> tuple[Path, str, list[dict]]:
    """Predetermined labels are visibly synthetic; tests may inject explicit invalid cases."""
    store.require_synthetic(root)
    actor_id = manifest.plan.annotators[actor].annotator_id
    annotations = []
    for i, record_id in enumerate(manifest.selected_ids):
        topic = "delayed_processing" if i < 4 else "complex_procedure"
        sentiment = "negative" if i < 4 else "neutral" if i < 6 else "positive"
        severity = "low" if i < 4 else "medium" if i < 6 else "high"
        if actor == "B" and i in {3, 4}:
            topic = "complex_procedure" if i == 3 else "delayed_processing"
            sentiment = "neutral" if i == 3 else "negative"
            severity = "medium" if i == 3 else "low"
        row = BlankAnnotation(
            feedback_id=record_id,
            dataset_version=manifest.dataset_version,
            taxonomy_version=VERSION,
            taxonomy_checksum=CHECKSUM,
            source_id=manifest.source_id,
            dataset_type="SYNTHETIC",
            annotator_id=actor_id,
        ).model_dump(mode="json")
        row.update(
            topic_label=topic,
            sentiment_label=sentiment,
            severity_label=severity,
            multiple_issues=False,
            annotation_status="SUBMITTED",
            topic_justification="SYNTHETIC: nhãn lập trình sẵn để kiểm tra phần mềm.",
            sentiment_justification="SYNTHETIC: nhãn kiểm tra, không phải đánh giá con người.",
            severity_justification="SYNTHETIC: ví dụ kiểm tra có tác động giả lập.",
            annotated_at=datetime.now(UTC).isoformat(),
        )
        row.update((modifications or {}).get(i, {}))
        annotations.append(row)
    path = pilot.delivery(root, manifest.pilot_id, actor) / f"submitted_r{revision}.csv"
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for row in annotations:
            values = row.copy()
            values["multiple_issues"] = "true" if values["multiple_issues"] else "false"
            writer.writerow(values)
    write_json(metadata_path(path), pilot.source_metadata(manifest.plan).model_dump())
    _, checksum = pilot.load_pilot(root, registry, manifest.pilot_id)
    assigned, _ = store.bundle(pilot.location(root, manifest.pilot_id) / "assignments" / actor)
    history = pilot.submissions(root, manifest.pilot_id, actor)
    reference = f"synthetic_{actor.lower()}_r{revision}"
    store.private_directory(store.base(root) / "requests")
    receipt = pilot.SubmissionReceipt(
        decision_ref=reference,
        pilot_id=manifest.pilot_id,
        pilot_checksum=checksum,
        actor=actor,
        revision=revision,
        previous_submission_checksum=history[-1][1] if history else None,
        input_checksum=official.file_digest(path),
        context_checksum=assigned["assignment.json"]["context_checksum"],
        annotator_id=actor_id,
        independent_attestation=True,
        human_verified=False,
        reviewed_at=datetime.now(UTC).isoformat(),
        evidence_reference="synthetic_no_human_evidence",
    )
    write_json(pilot.requests(root, reference), receipt.model_dump())
    return path, reference, annotations


def synthetic_decision(
    root: Path,
    registry: Registry,
    manifest: pilot.PilotManifest,
    rows: list[dict],
    reference: str = "synthetic_adjudication",
) -> str:
    store.require_synthetic(root)
    report, _ = pilot.agreement_report(root, registry, manifest.pilot_id)
    finals = [
        {
            **row,
            "annotator_id": manifest.plan.adjudicator.annotator_id,
            "topic_justification": "SYNTHETIC: quyết định kiểm tra được lập trình sẵn.",
            "annotated_at": datetime.now(UTC).isoformat(),
        }
        for row in rows
    ]
    decision = pilot.AdjudicationDecision(
        decision_ref=reference,
        pilot_id=manifest.pilot_id,
        pilot_checksum=report["pilot_checksum"],
        submission_checksums=report["submission_checksums"],
        adjudicator_id=manifest.plan.adjudicator.annotator_id,
        reviewed_at=datetime.now(UTC).isoformat(),
        evidence_reference="synthetic_no_human_evidence",
        human_verified=False,
        approve_final=True,
        final_records=finals,
    )
    write_json(pilot.requests(root, reference), decision.model_dump(mode="json"))
    return reference


def smoke(project_root: Path, registry: Registry) -> dict:
    with TemporaryDirectory(prefix="pfa-pilot-synthetic-") as temporary:
        root = Path(temporary)
        protect_directory(root)
        with store.synthetic_session(root):
            manifest = create_synthetic(root, project_root)
            sets = []
            for actor in ("A", "B"):
                pilot.export_assignment(root, registry, manifest.pilot_id, actor)
                path, reference, annotations = synthetic_submission(root, registry, manifest, actor)
                pilot.import_submission(root, registry, manifest.pilot_id, actor, path, reference)
                sets.append(annotations)
            report, _ = pilot.agreement_report(root, registry, manifest.pilot_id)
            expected = {"topic": 0.5, "sentiment": 0.6, "severity": 0.6}
            if any(
                abs(report["tasks"][task]["kappa"] - value) > 1e-12
                for task, value in expected.items()
            ):
                raise AssertionError("Synthetic agreement calculation differs from known fixture")
            pilot.export_review(root, registry, manifest.pilot_id)
            reference = synthetic_decision(root, registry, manifest, sets[0])
            final = pilot.adjudicate(root, registry, manifest.pilot_id, reference)
            verified = pilot.verify_pilot(root, registry, manifest.pilot_id)
        metrics = {
            task: {
                name: report["tasks"][task][name]
                for name in ("kappa", "raw_agreement_percent", "comparable_pairs")
            }
            for task in expected
        }
    return {
        "status": "PILOT_SMOKE_PASS_SYNTHETIC",
        "dataset_type": "SYNTHETIC",
        "metrics_usage": "SOFTWARE_TEST_ONLY",
        "human_agreement_measured": False,
        "record_count": 8,
        "agreement": metrics,
        "adjudication": final["status"],
        "verification": verified["status"],
        "human_gold": False,
        "gold_count": 0,
        "temporary_storage_cleaned": not root.exists(),
        "real_approval_records_created": False,
    }
