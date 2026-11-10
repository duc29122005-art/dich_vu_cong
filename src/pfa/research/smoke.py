"""Disposable invented observations, not real participant measurements or model results."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot_store as store
from pfa.annotation.agreement import TASKS
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked
from pfa.ml import evaluation, evaluation_policy
from pfa.research import assignments, protocol, reporting, rq1, rq3, rq4, validation
from pfa.research.schemas import (
    AlertWindow,
    Case,
    ConsentEvent,
    Labels,
    NumericalCheck,
    Observation,
    Participant,
    Payload,
    Questionnaire,
    Request,
    Usability,
)

MODE = "SYNTHETIC_ENGINEERING_TEST"


def fixture(rules):
    participants = [
        Participant(
            mode=MODE,
            participant_id=f"p_{i:016x}",
            consent_reference=f"consent_{i}",
            eligibility_reference="invented_only",
        )
        for i in range(24)
    ]
    cases = [
        Case(
            case_id=f"case_{i}",
            group_id=f"group_{i}",
            source_id="synthetic_demo",
            source_version="invented_v1",
            mode=MODE,
            role="EXPERIMENT_INDEPENDENT" if i < 60 else "DESCRIPTIVE",
            difficulty=["easy", "medium", "hard"][i % 3],
            basis="adjudicated",
            labels=Labels(
                topic=list(TASKS["topic"])[i % 8] if i < 68 else None,
                sentiment="negative",
                severity="high" if i % 3 == 0 else "low",
            ),
            reference_gold_id=f"invented_gold_{i}" if i < 60 else None,
            event_time=datetime(2025, 1, 1, tzinfo=UTC) if i % 2 else None,
            label_provenance_ref="invented_fixture_not_human_gold",
        )
        for i in range(72)
    ]
    consents = [
        ConsentEvent(
            mode=MODE,
            consent_reference=p.consent_reference,
            participant_id=p.participant_id,
            sequence=1,
            state="GRANTED",
            occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
            evidence_reference="synthetic_consent_not_real",
            information_sheet_version="participant-info-1",
        )
        for p in participants
    ]
    payload = Payload(cases=cases, participants=participants, consent_events=consents)
    manifest = assignments.generate(
        participants,
        cases[:60],
        rules,
        "engineering_experiment",
        MODE,
        forbidden_case_ids=set(),
        forbidden_groups=set(),
    )
    return payload, manifest


def measurements(payload, manifest):
    cases = {c.case_id: c for c in payload.cases}
    people = {p.participant_id: p for p in payload.participants}
    clocks, observations = {}, []
    for index, assigned in enumerate(manifest["assignments"][:-1]):
        person = assigned["participant_id"]
        start = clocks.get(person, datetime(2025, 1, 2, tzinfo=UTC))
        seconds = (60 if assigned["condition"] == "MANUAL_ONLY" else 40) + index % 3
        end = start + timedelta(seconds=seconds)
        clocks[person] = end + timedelta(seconds=2)
        case = cases[assigned["case_id"]]
        assisted = assigned["condition"] == "AI_ASSISTED"
        abandoned = index == 0
        observations.append(
            Observation(
                mode=MODE,
                experiment_id=assigned["experiment_id"],
                assignment_id=assigned["assignment_id"],
                participant_id=person,
                session_id="synthetic_session",
                case_id=case.case_id,
                condition=assigned["condition"],
                condition_order=assigned["condition_order"],
                model_version="synthetic_mock_v1" if assisted else None,
                model_versions={task: "synthetic_mock_v1" for task in TASKS} if assisted else None,
                task_start_time=start,
                task_end_time=end,
                duration_seconds=seconds,
                completion_status="ABANDONED" if abandoned else "COMPLETED",
                reviewer_topic=case.labels.topic if not abandoned else None,
                reviewer_sentiment=case.labels.sentiment if not abandoned else None,
                reviewer_severity=case.labels.severity if not abandoned else None,
                reference_gold_id=case.reference_gold_id,
                ai_suggestion_shown=assisted,
                ai_suggestion=case.labels if assisted else None,
                ai_suggestion_accepted=True if assisted and not abandoned else None,
                override_flag=False if assisted and not abandoned else None,
                review_reason="TIMEOUT" if abandoned else "CONFIRM",
                measurement_source="SYNTHETIC_FIXTURE",
                consent_reference=people[person].consent_reference,
                protocol_version="research-protocol-1",
            )
        )
    person = payload.participants[0]
    start = datetime(2025, 1, 3, tzinfo=UTC)
    return Payload.model_validate(
        {
            **payload.model_dump(),
            "observations": observations,
            "usability": [
                Usability(
                    mode=MODE,
                    participant_id=person.participant_id,
                    consent_reference=person.consent_reference,
                    task_id=task,
                    answer_code=values["answer"],
                    completion_status="COMPLETED",
                    task_start_time=start,
                    task_end_time=start + timedelta(seconds=30),
                    duration_seconds=30,
                    dashboard_version="dashboard_demo_v1",
                )
                for task, values in rq3.TASKS.items()
            ],
            "questionnaires": [
                Questionnaire(
                    mode=MODE,
                    participant_id=person.participant_id,
                    consent_reference=person.consent_reference,
                    collected_at=start,
                    perceived_usefulness=3,
                    perceived_workload=50,
                )
            ],
            "numerical_checks": [
                NumericalCheck(metric="total", expected=12, observed=12, reference="invented_count")
            ],
            "alert_windows": [
                AlertWindow(
                    window_id="invented_window",
                    eligible=True,
                    triggered=True,
                    reference_event=True,
                    reference="invented_reference_not_incident",
                )
            ],
        }
    )


def package(root, rules, payload, identity="invented_input"):
    checksum = store.publish(
        protocol.base(root) / "inputs" / identity, {"payload.json": payload.model_dump(mode="json")}
    )
    request = Request(
        mode=MODE,
        experiment_id="engineering_experiment",
        protocol_version=rules.version,
        protocol_sha256=store.digest(rules.model_dump()),
        taxonomy_version=VERSION,
        taxonomy_checksum=CHECKSUM,
        source_id="synthetic_demo",
        payload_id=identity,
        payload_sha256=checksum,
        case_membership=[c.case_id for c in payload.cases],
        assistance_models={task: "synthetic_mock_v1" for task in TASKS},
    )
    path = root / (identity + ".json")
    path.write_text(request.model_dump_json(), encoding="utf-8")
    return path


def smoke(project_root: Path):
    with TemporaryDirectory(prefix="pfa-research-") as temporary:
        root = Path(temporary)
        for name in (
            "configs/research_protocol_v1.yaml",
            "configs/evaluation_v1.yaml",
            "configs/dataset_sources.yaml",
            "docs/EXPERIMENT_PROTOCOL.md",
            "configs/analytics_v1.yaml",
            "docs/KPI_DICTIONARY.md",
            "docs/RESEARCH_PARTICIPANT_CONSENT.md",
        ):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((project_root / name).read_bytes())
        with store.synthetic_session(root):
            rules = protocol.load(root)
            payload, manifest = fixture(rules)
            assert manifest == assignments.generate(
                payload.participants,
                payload.cases[:60],
                rules,
                "engineering_experiment",
                MODE,
                forbidden_case_ids=set(),
                forbidden_groups=set(),
            )
            before = package(root, rules, payload, "before_collection")
            frozen = reporting.allocation(root, before)
            assert frozen["orders"] == {"AB": 12, "BA": 12}
            measured = measurements(payload, manifest)
            after = package(root, rules, measured, "after_collection")
            result = reporting.report(root, after)
            assert result["collection"] == {
                "assigned": 144,
                "observed": 143,
                "missing_observations": 1,
            }
            assert result["results"]["rq4"]["completed_case_time_seconds"]["interval"] is not None
            assert result["results"]["rq2"]["status"] == "BLOCKED_ON_RESEARCH_DATA"
            assert result["results"]["rq3"]["numerical_correctness"][0]["passed"]
            assert result["results"]["rq3"]["human_usability"]["tasks"][0]["accuracy"]["share"] == 1
            assert result == reporting.report(root, after)
            topics = rq1.analyze(payload.cases[60:], "adjudicated")
            assert topics["total_eligible_cases"] == 12 and topics["coverage"]["numerator"] == 8
            assert rq3.alert_quality([(False, True, True)])["status"] == "INSUFFICIENT_EVIDENCE"
            missing_consent = Payload.model_validate(
                {**measured.model_dump(), "consent_events": []}
            )
            try:
                validation.consent(missing_consent, MODE)
            except IngestionBlocked:
                pass
            else:
                raise AssertionError("Missing consent was accepted")
            empty = rq4.analyze(Payload(), {"assignments": []}, rules)
            assert empty["status"] == "INSUFFICIENT_EVIDENCE"
            # Reuse STEP11 metrics/compatibility; invented vectors are not model runs.
            binding = {"dataset_type": "SYNTHETIC", "dataset_version": "invented_v1"}
            for task, labels in TASKS.items():
                descriptor = {
                    "dataset": binding,
                    "task": task,
                    "labels": list(labels),
                    "taxonomy_checksum": CHECKSUM,
                    "taxonomy_version": VERSION,
                    "preprocessing": {"normalization": "conservative-1"},
                    "model_kind": "SYNTHETIC_FIXTURE",
                    "family": "lr",
                }
                evaluation.compatible([descriptor], binding)
                assert evaluation_policy.metrics(list(labels), list(labels), task)["accuracy"] == 1
            try:
                corpus.model_selection(root, None, "not_a_dataset", "test")
            except IngestionBlocked:
                pass
            else:
                raise AssertionError("Protected holdout reader unexpectedly allowed access")
            exported = json.dumps(result)
            assert all(p.participant_id not in exported for p in payload.participants)
            try:
                reporting.allocation(root, before)
            except ValueError:
                pass
            else:
                raise AssertionError("Immutable allocation was overwritten")
        # Internal synthetic capability is gone: CLI cannot treat fixtures as research evidence.
        try:
            reporting.report(root, after)
        except IngestionBlocked:
            pass
        else:
            raise AssertionError("Synthetic research separation failed")
    return {
        "status": "RESEARCH_SMOKE_PASS_SYNTHETIC",
        "mode": MODE,
        "notice": "INVENTED PARTICIPANTS AND MEASUREMENTS — NOT RESEARCH FINDINGS",
        "synthetic_participants": 24,
        "assignments": 144,
        "observations": 143,
        "order_counts": {"AB": 12, "BA": 12},
        "missing_observations": 1,
        "rq1_denominators_verified": True,
        "rq2_step11_metrics_reused": True,
        "crossed_bootstrap_verified": True,
        "consent_and_missing_support_verified": True,
        "research_results": "BLOCKED",
        "test_holdout": "PROTECTED",
        "test_labels_read": False,
        "temporary_storage_cleaned": not root.exists(),
    }
