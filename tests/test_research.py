"""Offline prospective protocol, collection, consent and analysis regression checks."""

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pfa.annotation import pilot_store as store
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.ml import evaluation, evaluation_policy, model_registry
from pfa.research import assignments, commands, protocol, reporting, rq1, rq2, rq3, rq4, validation
from pfa.research.schemas import TEMPLATES, Observation, Payload, Request
from pfa.research.smoke import MODE, fixture, measurements, package, smoke
from pfa.research.statistics import paired_contrast, ratio

PROJECT = Path(__file__).resolve().parents[1]


def test_audit_tied_clocks_preserve_review_version_order(monkeypatch):
    from uuid import UUID

    from pfa.db.models import ReviewEvent
    from pfa.db.repository import Repository
    from pfa.db.smoke import smoke as database_smoke

    # Force opposite UUID order and one clock tick for every event, including conflict.
    ids = iter([4, 3, 2, 1])
    original = Repository.add_event

    def tied_event(self, *args, **kwargs):
        original(self, *args, **kwargs)
        event = next(e for e in self.session.new if isinstance(e, ReviewEvent))
        event.review_event_id = UUID(int=next(ids))
        event.occurred_at = datetime(2025, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(Repository, "add_event", tied_event)
    assert database_smoke(PROJECT)["audit_event_count"] == 4


@pytest.fixture
def root(tmp_path):
    for name in (
        "configs/research_protocol_v1.yaml",
        "configs/evaluation_v1.yaml",
        "configs/dataset_sources.yaml",
        "docs/EXPERIMENT_PROTOCOL.md",
        "configs/analytics_v1.yaml",
        "docs/KPI_DICTIONARY.md",
        "docs/RESEARCH_PARTICIPANT_CONSENT.md",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((PROJECT / name).read_bytes())
    return tmp_path


@pytest.fixture
def rules(root):
    return protocol.load(root)


@pytest.fixture
def data(rules):
    return fixture(rules)


def changed(model, **values):
    return type(model).model_validate({**model.model_dump(), **values})


def test_protocol_pins_existing_step11(root, rules):
    assert rules.evaluation_config_sha256 == store.file_checksum(
        root / "configs/evaluation_v1.yaml"
    )
    assert rules.supervisor is None and rules.confirmed_independent_annotators == 0
    assert rules.researcher == "Dương Thị Hồng Vân"


@pytest.mark.parametrize(
    "file",
    [
        "configs/evaluation_v1.yaml",
        "docs/EXPERIMENT_PROTOCOL.md",
        "configs/analytics_v1.yaml",
        "docs/KPI_DICTIONARY.md",
        "docs/RESEARCH_PARTICIPANT_CONSENT.md",
    ],
)
def test_changed_step11_requires_review(root, file):
    with (root / file).open("a") as stream:
        stream.write("\n")
    with pytest.raises(IngestionBlocked):
        protocol.load(root)


@pytest.mark.parametrize("count", [1, 3, 10, 23, 24])
def test_counterbalance_deterministic_and_no_exposure(data, rules, count):
    payload, _ = data
    people = payload.participants[:count]
    cases = payload.cases[:60]

    def allocate():
        return assignments.generate(
            people,
            cases,
            rules,
            "experiment",
            MODE,
            forbidden_case_ids=set(),
            forbidden_groups=set(),
        )

    manifest = allocate()
    assert manifest == allocate()
    assert abs(manifest["order_counts"].get("AB", 0) - manifest["order_counts"].get("BA", 0)) <= 1
    for person in people:
        rows = [a for a in manifest["assignments"] if a["participant_id"] == person.participant_id]
        assert len(rows) == 6 and len({r["case_id"] for r in rows}) == 6
        assert sorted(r["difficulty"] for r in rows if r["condition"] == "MANUAL_ONLY") == sorted(
            r["difficulty"] for r in rows if r["condition"] == "AI_ASSISTED"
        )
    assert "reference_gold_id" not in json.dumps(manifest) and "labels" not in json.dumps(
        manifest
    ).replace("holdout_labels_read", "")


@pytest.mark.parametrize("reason", ["case", "group", "mode", "duplicate", "role", "sparse"])
def test_assignment_boundaries(data, rules, reason):
    payload, _ = data
    cases = payload.cases[:60]
    forbidden, groups = set(), set()
    if reason == "case":
        forbidden.add(cases[0].case_id)
    elif reason == "group":
        groups.add(cases[0].group_id)
    elif reason == "mode":
        cases = [changed(cases[0], mode="AUTHORIZED_RESEARCH"), *cases[1:]]
    elif reason == "duplicate":
        cases = [cases[0], *cases]
    elif reason == "role":
        cases = [changed(cases[0], role="DESCRIPTIVE"), *cases[1:]]
    else:
        cases = cases[:2]
    with pytest.raises((IngestionError, IngestionBlocked)):
        assignments.generate(
            payload.participants,
            cases,
            rules,
            "experiment",
            MODE,
            forbidden_case_ids=forbidden,
            forbidden_groups=groups,
        )


def test_rq1_denominators_missing_and_taxonomy(data):
    payload, _ = data
    result = rq1.analyze(payload.cases[60:], "adjudicated")
    assert result["total_eligible_cases"] == 12
    assert result["coverage"] == ratio(8, 12)
    assert result["missing_labels"] == ratio(4, 12)
    assert [r["label"] for r in result["topics"]] == list(evaluation_policy.baseline.TASKS["topic"])
    assert sum(r["numerator"] for r in result["topics"]) == 8
    assert result["missing_event_time"] == ratio(6, 12)
    assert result["uncertainty"]["interval"] is None


def test_rq1_duplicate_and_basis_rejected(data):
    cases = data[0].cases
    with pytest.raises(IngestionError):
        rq1.analyze([cases[0], cases[0]], "adjudicated")
    with pytest.raises(IngestionError):
        rq1.analyze(cases, "prediction")
    assert rq1.analyze([], "prediction")["coverage"]["share"] is None


@pytest.mark.parametrize("basis", ["prediction", "reviewed", "adjudicated"])
def test_rq1_bases_are_explicit(data, basis):
    result = rq1.analyze([changed(data[0].cases[0], basis=basis)], basis)
    assert result["basis"] == basis


def test_observation_schema(data):
    payload = measurements(*data)
    assert (
        Observation.model_validate_json(payload.observations[0].model_dump_json())
        == payload.observations[0]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration_seconds", -1),
        ("duration_seconds", float("nan")),
        ("duration_seconds", 999),
        ("task_end_time", None),
        ("task_start_time", "2025-01-01T00:00:00"),
        ("reviewer_topic", "invented_label"),
        ("protocol_version", "unknown"),
        ("measurement_source", "MANUAL_CLOCK"),
        ("perceived_usefulness", 9),
        ("participant_id", "person@example.com"),
        ("text", "private input"),
    ],
)
def test_observation_invalid_values(data, field, value):
    row = next(r for r in measurements(*data).observations if r.completion_status == "COMPLETED")
    with pytest.raises(ValidationError):
        changed(row, **{field: value})


def test_unknown_severity_and_manual_assistance(data, rules):
    payload, manifest = data
    measured = measurements(payload, manifest)
    row = next(
        r
        for r in measured.observations
        if r.condition == "MANUAL_ONLY" and r.completion_status == "COMPLETED"
    )
    assert changed(row, reviewer_severity="unknown").reviewer_severity == "unknown"
    with pytest.raises(ValidationError):
        changed(row, model_version="synthetic_mock_v1")
    assisted = next(r for r in measured.observations if r.ai_suggestion_accepted)
    with pytest.raises(ValidationError):
        changed(assisted, override_flag=True)
    with pytest.raises(ValidationError):
        changed(assisted, model_versions={"topic": "synthetic_mock_v1"})
    altered = [changed(c, reference_gold_id=None) for c in payload.cases]
    no_gold = changed(measured, cases=altered)
    assert (
        rq4.analyze(no_gold, manifest, rules)["independent_gold_accuracy"]["status"]
        == "INSUFFICIENT_EVIDENCE"
    )


@pytest.mark.parametrize(
    "reason", ["missing", "withdrawn", "late", "reference", "mixed_mode", "unverified"]
)
def test_consent_fail_closed(data, reason):
    measured = measurements(*data)
    first = measured.observations[0]
    events = list(measured.consent_events)
    if reason == "missing":
        events = []
    elif reason == "withdrawn":
        base = next(e for e in events if e.participant_id == first.participant_id)
        events.append(
            changed(
                base, sequence=2, state="WITHDRAWN", occurred_at=datetime(2025, 2, 1, tzinfo=UTC)
            )
        )
    elif reason == "late":
        events = [changed(e, occurred_at=datetime(2025, 2, 1, tzinfo=UTC)) for e in events]
    elif reason == "reference":
        events = [changed(e, consent_reference="wrong") for e in events]
    elif reason == "mixed_mode":
        events = [changed(e, mode="AUTHORIZED_RESEARCH") for e in events]
    with pytest.raises(IngestionBlocked):
        validation.consent(
            changed(measured, consent_events=events),
            MODE if reason != "unverified" else "AUTHORIZED_RESEARCH",
        )


@pytest.mark.parametrize("mutation", ["duplicate", "outside", "wrong_gold", "clock", "order"])
def test_observation_allocation_integrity(data, mutation):
    payload, manifest = data
    measured = measurements(payload, manifest)
    rows = list(measured.observations)
    if mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "outside":
        rows[0] = changed(rows[0], assignment_id="unassigned")
    elif mutation == "wrong_gold":
        rows[0] = changed(rows[0], reference_gold_id="wrong_gold")
    elif mutation == "clock":
        rows[1] = changed(
            rows[1],
            task_start_time=rows[0].task_start_time,
            task_end_time=rows[0].task_start_time + timedelta(seconds=rows[1].duration_seconds),
        )
    else:
        rows[0] = changed(
            rows[0], condition_order="BA" if rows[0].condition_order == "AB" else "AB"
        )
    with pytest.raises((IngestionBlocked, IngestionError)):
        validation.observations(
            changed(measured, observations=rows), manifest, "engineering_experiment"
        )


def test_missing_and_abandoned_are_not_completed(data, rules):
    payload, manifest = data
    measured = measurements(payload, manifest)
    counts = validation.observations(measured, manifest, "engineering_experiment")
    result = rq4.analyze(measured, manifest, rules)
    assert counts == {"assigned": 144, "observed": 143, "missing_observations": 1}
    assert sum(c["abandoned"] for c in result["conditions"].values()) == 1
    assert sum(c["completed"] for c in result["conditions"].values()) == 142
    assert all(c["completion_rate"]["denominator"] == 72 for c in result["conditions"].values())


def test_cluster_bootstrap_reproducible_and_not_row_independent(rules):
    records = [
        (f"p{i}", f"group{j}", condition, value, "AB" if i % 2 else "BA")
        for i in range(24)
        for j in range(24)
        for condition, value in (("MANUAL_ONLY", 10.0), ("AI_ASSISTED", 8.0))
    ]
    first = paired_contrast(records, rules)
    assert first == paired_contrast(records, rules)
    assert first["difference_ai_minus_manual"] == -2
    assert first["interval"] == [-2.0, -2.0]
    assert first["p_value"] is None and first["paired_standardized_difference"] is None
    assert paired_contrast(records[:48] * 100, rules)["status"] == "INSUFFICIENT_EVIDENCE"
    assert paired_contrast([], rules)["interval"] is None


def test_cluster_order_and_case_support_guards(rules):
    for people, groups, orders in ((30, 1, True), (1, 30, True), (30, 30, False)):
        records = [
            (f"p{i}", f"g{j}", c, float(j), "AB" if not orders or i % 2 else "BA")
            for i in range(people)
            for j in range(groups)
            for c in ("MANUAL_ONLY", "AI_ASSISTED")
        ]
        assert paired_contrast(records, rules)["interval"] is None


def test_rq3_alert_reference_and_task_scores(data):
    measured = measurements(*data)
    result = rq3.usability(measured.usability, measured.questionnaires)
    assert all(task["accuracy"]["share"] == 1 for task in result["tasks"])
    alerts = rq3.alert_quality(
        [
            (True, True, True),
            (True, True, False),
            (True, False, True),
            (True, False, False),
            (False, True, True),
            (True, True, None),
        ]
    )
    assert [
        alerts[key]
        for key in ("true_positive", "false_positive", "false_negative", "true_negative")
    ] == [1] * 4
    assert alerts["precision"]["share"] == 0.5
    assert alerts["excluded_windows"] == 2
    assert rq3.alert_quality([])["false_positive_rate"]["share"] is None
    assert rq3.usability([], [])["status"] == "BLOCKED_ON_EXPERIMENT"


def test_rq2_reuses_step11_and_rejects_tiny_research():
    binding = {"dataset_type": "RESEARCH"}
    descriptor = {
        "dataset": binding,
        "task": "severity",
        "labels": ["low", "medium", "high"],
        "taxonomy_checksum": "frozen",
        "taxonomy_version": "1.0.0",
        "preprocessing": {"normalization": "conservative-1"},
        "family": "phobert",
        "model_kind": "SYNTHETIC_TINY_MODEL",
    }
    with pytest.raises(IngestionBlocked):
        evaluation.compatible([descriptor], binding)
    with pytest.raises(IngestionError):
        evaluation.compatible([{**descriptor, "labels": ["high", "medium", "low"]}], binding)
    assert evaluation_policy.metrics(["high"], ["low"], "severity")["severity_high_recall"] == 0
    assert rq2.final_summary(None, None, None, binding)["status"] == "BLOCKED_ON_RESEARCH_DATA"


def test_no_real_permission_before_payload_reads(root, rules, monkeypatch):
    payload, _ = fixture(rules)
    with store.synthetic_session(root):
        source = package(root, rules, payload)
    original = json.loads(source.read_text())
    original.update(
        mode="AUTHORIZED_RESEARCH",
        source_id="public_service_official",
        dataset_version="not_available",
    )
    source.write_text(json.dumps(original))

    def forbidden(*args, **kwargs):
        pytest.fail("Observation payload was accessed before permission gate")

    monkeypatch.setattr(store, "bundle", forbidden)
    with pytest.raises(PermissionError):
        validation.authorize_request(root, source, rules)


def test_synthetic_capability_required(root, rules, data):
    with store.synthetic_session(root):
        source = package(root, rules, data[0])
    with pytest.raises(IngestionBlocked):
        validation.authorize_request(root, source, rules)


def test_report_reproducible_private_and_immutable(root, rules, data, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Protected holdout access")

    monkeypatch.setattr(corpus, "evaluation_data", forbidden)
    with store.synthetic_session(root):
        source = package(root, rules, data[0], "allocation_source")
        reporting.allocation(root, source)
        with pytest.raises(IngestionError):
            reporting.allocation(root, source)
        measured = measurements(*data)
        after = package(root, rules, measured, "observed_source")
        result = reporting.report(root, after)
        assert result == reporting.report(root, after)
        text = json.dumps(result)
        assert all(p.participant_id not in text for p in measured.participants)
        assert all(r.case_id not in text for r in measured.cases)
        assert not result["test_labels_read"] and not result["scientific_conclusions_generated"]
        assert result["results"]["rq2"]["models"] == []
        path = protocol.base(root) / "inputs/observed_source/payload.json"
        path.write_text("{}")
        with pytest.raises(IngestionError):
            reporting.report(root, after)


def test_assignment_observation_reassignment_denied(root, rules, data):
    with store.synthetic_session(root):
        source = package(root, rules, data[0], "before")
        reporting.allocation(root, source)
        measured = measurements(*data)
        changed_cases = [changed(measured.cases[0], difficulty="hard"), *measured.cases[1:]]
        after = package(root, rules, changed(measured, cases=changed_cases), "after")
        with pytest.raises(IngestionBlocked):
            reporting.report(root, after)
        with pytest.raises(IngestionBlocked):
            reporting.allocation(root, after)


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_blank_templates_and_schema_validation(root, name):
    target = root / "blank"
    protocol.templates(target)
    assert validation.validate_file(target / (name + ".csv"), name)["records"] == 0
    assert validation.validate_file(target / (name + ".jsonl"), name)["records"] == 0
    assert (
        json.loads((target / (name + ".schema.json")).read_text())["additionalProperties"] is False
    )
    with pytest.raises(IngestionError):
        protocol.templates(target)


def test_csv_jsonl_observation_validation(root, data):
    row = next(r for r in measurements(*data).observations if r.condition == "MANUAL_ONLY")
    jsonl = root / "observations.jsonl"
    jsonl.write_text(row.model_dump_json() + "\n")
    assert validation.validate_file(jsonl, "manual_observations")["records"] == 1
    with pytest.raises(IngestionError):
        validation.validate_file(jsonl, "assisted_observations")
    table = root / "observations.csv"
    with table.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(Observation.model_fields)
        writer.writerow(
            json.dumps(v) if v is not None else "" for v in row.model_dump(mode="json").values()
        )
    assert validation.validate_file(table, "manual_observations")["records"] == 1
    jsonl.write_text('{"participant_id":"private@example.com"}')
    with pytest.raises(IngestionError, match="submitted values withheld") as error:
        validation.validate_file(jsonl, "manual_observations")
    assert "private@example.com" not in str(error.value)


def test_report_denied_no_consent_and_no_model_promotion(root, rules, data, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Research report attempted model promotion")

    monkeypatch.setattr(model_registry, "activate", forbidden)
    with store.synthetic_session(root):
        source = package(root, rules, data[0], "before")
        reporting.allocation(root, source)
        measured = changed(measurements(*data), consent_events=[])
        after = package(root, rules, measured, "after")
        with pytest.raises(IngestionBlocked):
            reporting.report(root, after)


def test_cli_safe_exits_and_existing_parser(root, capsys, monkeypatch):
    from pfa.cli import main

    monkeypatch.setenv("PFA_PROJECT_ROOT", str(root))
    assert main(["research", "status"]) == 0
    assert main(["research", "protocol-check"]) == 0
    source = root / "invalid.json"
    source.write_text('{"secret":"never_print_me"}')
    assert main(["research", "report", "--source", str(source)]) == 2
    assert "never_print_me" not in capsys.readouterr().out
    with store.synthetic_session(root):
        payload, _ = fixture(protocol.load(root))
        path = package(root, protocol.load(root), payload)
    result, code = commands.run(
        root, SimpleNamespace(research_action="report", source=path, rq="rq4")
    )
    assert code == 3 and result["status"] == "BLOCKED_ON_EXPERIMENT"


def test_smoke_offline_and_cleanup():
    result = smoke(PROJECT)
    assert result["status"] == "RESEARCH_SMOKE_PASS_SYNTHETIC"
    assert result["temporary_storage_cleaned"] and not result["test_labels_read"]


def test_holdout_rejected_before_payload_read(root, rules, data, monkeypatch):
    with store.synthetic_session(root):
        source = package(root, rules, data[0])
    request = json.loads(source.read_text())
    request.update(
        mode="AUTHORIZED_RESEARCH",
        source_id="public_service_official",
        dataset_version="approved_dataset",
    )
    source.write_text(json.dumps(request))
    monkeypatch.setattr(validation, "require_access", lambda *a: None)
    monkeypatch.setattr(validation.approval, "require_taxonomy", lambda *a: "approved")
    monkeypatch.setattr(
        corpus,
        "_authorized_manifest",
        lambda *a: (
            None,
            {
                "dataset_type": "RESEARCH",
                "provenance": {"plan": {"source_id": "public_service_official"}},
                "membership": {"test": [data[0].cases[0].case_id]},
            },
        ),
    )

    def forbidden(*a):
        pytest.fail("Protected labels could be read before membership exclusion")

    monkeypatch.setattr(store, "bundle", forbidden)
    with pytest.raises(IngestionBlocked, match="holdout"):
        validation.authorize_request(root, source, rules)


def test_independent_gold_protects_existing_test_members(data, monkeypatch):
    from pfa.research.schemas import GoldReference

    payload = changed(
        data[0],
        gold_references=[
            GoldReference(
                mode=MODE,
                reference_gold_id="gold",
                case_id="case_0",
                pilot_id="pilot",
                adjudicated_sha256="a" * 64,
            )
        ],
    )
    monkeypatch.setattr(
        validation.pilot,
        "load_pilot",
        lambda *a: (SimpleNamespace(selected_ids=["protected_case"]), "checksum"),
    )

    def forbidden(*a):
        pytest.fail("Pilot gold read before protected membership check")

    monkeypatch.setattr(validation.pilot, "verify_pilot", forbidden)
    with pytest.raises(IngestionBlocked):
        validation.independent_gold(
            None, None, payload, {"membership": {"test": ["protected_case"]}}
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol_sha256", "0" * 64),
        ("payload_id", "../outside"),
        ("taxonomy_version", "2.0.0"),
        ("taxonomy_checksum", "0" * 64),
    ],
)
def test_control_metadata_mismatches(root, rules, data, field, value):
    with store.synthetic_session(root):
        source = package(root, rules, data[0])
        document = json.loads(source.read_text())
        document[field] = value
        source.write_text(json.dumps(document))
        with pytest.raises((ValidationError, IngestionBlocked)):
            validation.authorize_request(root, source, rules)


def test_preview_is_reviewable_and_does_not_lock(root, rules, data):
    with store.synthetic_session(root):
        source = package(root, rules, data[0])
        result = reporting.allocation(root, source, preview=True)
        assert result == reporting.allocation(root, source, preview=True)
        assert result["status"] == "ALLOCATION_PREVIEW_NOT_APPROVED"
        assert not (protocol.base(root) / "allocations").exists()
        assert all(p.participant_id not in json.dumps(result) for p in data[0].participants)
        frozen = reporting.allocation(root, source)
        assert frozen["assigned"] == result["assigned"]


def test_private_evidence_required_for_real_consent(root, data, monkeypatch):
    calls = []

    def deny(*args):
        calls.append(args[2])
        raise IngestionBlocked("No actual protected consent evidence")

    monkeypatch.setattr(model_registry, "authorize", deny)
    with pytest.raises(IngestionBlocked):
        validation.consent(data[0], "HUMAN_FEASIBILITY_PILOT", root)
    assert calls == ["VERIFY_CONSENT_EVENT"]


def test_no_pilot_promotion_by_changing_mode(root, rules, data):
    with store.synthetic_session(root):
        source = package(root, rules, data[0])
        document = json.loads(source.read_text())
        document["mode"] = "HUMAN_FEASIBILITY_PILOT"
        source.write_text(json.dumps(document))
        with pytest.raises(IngestionBlocked):
            validation.authorize_request(root, source, rules)


def test_model_candidate_and_random_transformer_denied(root, rules, data, monkeypatch):
    with store.synthetic_session(root):
        source = package(root, rules, data[0])
    request = Request.model_validate(
        {
            **json.loads(source.read_text()),
            "mode": "AUTHORIZED_RESEARCH",
            "dataset_version": "approved_dataset",
        }
    )
    monkeypatch.setattr(reporting.baseline, "development", lambda *a: ({}, {}))
    monkeypatch.setattr(rq2, "final_summary", lambda *a: {"status": "AVAILABLE"})
    monkeypatch.setattr(
        model_registry,
        "view",
        lambda *a: {"record": {"model": {"dataset": {"dataset_type": "RESEARCH"}}}, "history": []},
    )
    with pytest.raises(IngestionBlocked, match="research-approved"):
        reporting.model_gate(root, None, request, Payload())
    monkeypatch.setattr(
        model_registry,
        "view",
        lambda *a: {
            "record": {
                "model": {
                    "dataset": {"dataset_type": "RESEARCH"},
                    "family": "phobert",
                    "model_kind": "SYNTHETIC_TINY_MODEL",
                }
            },
            "history": [{"action": "RESEARCH_APPROVED"}],
        },
    )
    with pytest.raises(IngestionBlocked, match="Tiny random"):
        reporting.model_gate(root, None, request, Payload())


@pytest.mark.parametrize("fault", [None, "dataset", "taxonomy", "sample", "tiny", "unsafe_path"])
def test_existing_rq2_manifests_and_mismatches(root, monkeypatch, fault):
    from copy import deepcopy

    from pfa.annotation.taxonomy import CHECKSUM, VERSION

    binding = {"dataset_type": "RESEARCH", "dataset_version": "approved_dataset"}
    descriptors = {
        family: {
            "dataset": binding,
            "task": "severity",
            "labels": ["low", "medium", "high"],
            "taxonomy_version": VERSION,
            "taxonomy_checksum": CHECKSUM,
            "preprocessing": {"normalization": "conservative-1"},
            "family": family,
            "model_kind": "PRETRAINED_PHOBERT" if family == "phobert" else family,
            "validation": {"macro_f1": 0.8},
        }
        for family in ("lr", "svm", "phobert")
    }
    experiment = {
        "dataset": binding,
        "models": {k: {"descriptor": d} for k, d in descriptors.items()},
        "protocol": evaluation_policy.Protocol().model_dump(),
    }
    if fault == "taxonomy":
        descriptors["lr"]["taxonomy_checksum"] = "0" * 64
    if fault == "tiny":
        descriptors["phobert"]["model_kind"] = "SYNTHETIC_TINY_MODEL"
    report = {
        "dataset_type": "RESEARCH",
        "status": "COMPLETED",
        "dataset": binding,
        "experiment_id": "experiment",
        "experiment_sha256": "a" * 64,
        "selected_by_task": {"severity": "lr"},
        "authorization": {"reference": "final_approval"},
        "models": {
            k: {
                "descriptor_sha256": store.digest(d),
                "metrics": evaluation_policy.metrics(
                    ["low", "medium", "high"], ["low", "medium", "high"], "severity"
                ),
                "exclusions": {},
                "review": {"review_rate": 1.0, "automated_coverage": 0.0},
            }
            for k, d in descriptors.items()
        },
    }
    if fault == "dataset":
        report["dataset"] = {**binding, "dataset_version": "different"}
    elif fault == "sample":
        report["models"]["svm"]["exclusions"] = {"missing": 1}
    elif fault == "unsafe_path":
        report["experiment_id"] = "../outside"

    def bundle(path):
        if path.parent.name == "final_results":
            return {"report.json": deepcopy(report)}, "b" * 64
        if path.parent.name == "experiments":
            return {"experiment.json": deepcopy(experiment)}, "a" * 64
        return {
            "lock.json": {"experiment_sha256": "a" * 64, "approval_ref": "lock_approval"}
        }, "c" * 64

    monkeypatch.setattr(store, "bundle", bundle)
    monkeypatch.setattr(model_registry, "authorize", lambda root, ref, *a: {"reference": ref})
    monkeypatch.setattr(
        model_registry, "inspect", lambda root, registry, identity: {"model": descriptors[identity]}
    )
    if fault:
        with pytest.raises((IngestionBlocked, IngestionError)):
            rq2.final_summary(root, None, "existing_evaluation", binding)
    else:
        result = rq2.final_summary(root, None, "existing_evaluation", binding)
        assert len(result["models"]) == 3 and not result["test_labels_read"]
        assert result["models"][0]["metrics"]["accuracy"] == 1


def test_official_templates_remain_blank():
    for name in TEMPLATES:
        for suffix in (".csv", ".jsonl"):
            assert (
                validation.validate_file(PROJECT / "templates/research" / (name + suffix), name)[
                    "records"
                ]
                == 0
            )
