"""Aggregate-only reproducible reports; missing approvals never become scientific results."""

import sys
from datetime import datetime
from importlib.metadata import version

from pfa.annotation import pilot_store as store
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.ml import baseline, model_registry
from pfa.research import assignments, protocol, rq1, rq2, rq3, rq4, validation


def status(root):
    rules = protocol.load(root)
    return {
        "status": "PROTOCOL_PREPARED_NOT_HUMAN_APPROVED",
        "protocol_version": rules.version,
        "protocol_sha256": store.digest(rules.model_dump()),
        "modes": ["SYNTHETIC_ENGINEERING_TEST", "HUMAN_FEASIBILITY_PILOT", "AUTHORIZED_RESEARCH"],
        "RQ1": "BLOCKED_ON_RESEARCH_DATA",
        "RQ2": "BLOCKED_ON_RESEARCH_DATA",
        "RQ3": "BLOCKED_ON_RESEARCH_DATA",
        "RQ4": "BLOCKED_ON_EXPERIMENT",
        "reason": "Prepared protocol only; governed report validation checks actual evidence",
        "test_holdout": "PROTECTED",
        "human_participants_created": 0,
    }


def case_gate(root, request, payload, registry, frozen):
    validation.unique(payload.cases, lambda c: c.case_id, "Duplicate research case")
    if request.mode != "AUTHORIZED_RESEARCH":
        return
    independent = [c for c in payload.cases if c.role == "EXPERIMENT_INDEPENDENT"]
    forbidden = {i for ids in frozen["membership"].values() for i in ids}
    if {c.case_id for c in independent} & forbidden:
        raise IngestionBlocked("Experiment cases overlap training, tuning or protected holdout")
    if independent:
        validation.independent_gold(root, registry, payload, frozen)
    descriptive = [c for c in payload.cases if c.role == "DESCRIPTIVE"]
    if descriptive:
        rows = {
            r.feedback_id: r
            for split in ("train", "validation")
            for r in corpus.model_selection(root, registry, request.dataset_version, split)
        }
        for case in descriptive:
            actual = rows.get(case.case_id)
            if (
                actual is None
                or case.basis != "adjudicated"
                or actual.source_id != case.source_id
                or actual.source_version != case.source_version
                or actual.group_id != case.group_id
                or actual.event_time != case.event_time
                or actual.domain_bucket != case.domain
                or actual.agency_bucket != case.agency
                or any(getattr(case.labels, task) != actual.labels[task] for task in baseline.TASKS)
            ):
                raise IngestionBlocked(
                    "RQ1 currently requires exact governed development gold; no test labels"
                )


def recheck(root, source, rules, request, payload):
    if protocol.load(root) != rules:
        raise IngestionBlocked("Research protocol changed during analysis")
    current, records, registry, frozen = validation.authorize_request(root, source, rules)
    if current != request or records != payload:
        raise IngestionBlocked("Research inputs changed during analysis")
    case_gate(root, current, records, registry, frozen)
    model_gate(root, registry, current, records)


def allocation(root, source, preview=False):
    rules = protocol.load(root)
    request, payload, registry, frozen = validation.authorize_request(root, source, rules)
    if payload.observations or payload.usability or payload.questionnaires:
        raise IngestionBlocked("Allocation must freeze before observations exist")
    for person in payload.participants:
        history = [e for e in payload.consent_events if e.participant_id == person.participant_id]
        if max(history, key=lambda e: e.sequence).state != "GRANTED":
            raise IngestionBlocked("Current consent required before assignment")
    case_gate(root, request, payload, registry, frozen)
    model_gate(root, registry, request, payload)
    cases = [c for c in payload.cases if c.role == "EXPERIMENT_INDEPENDENT"]
    forbidden = {c for ids in frozen["membership"].values() for c in ids} if frozen else set()
    manifest = assignments.generate(
        payload.participants,
        cases,
        rules,
        request.experiment_id,
        request.mode,
        forbidden_case_ids=forbidden,
        forbidden_groups=set(),
    )
    manifest["dataset_binding_sha256"] = store.digest(frozen) if frozen else None
    manifest["source_id"] = request.source_id
    manifest["implementation_sha256"] = protocol.implementation()
    manifest["assistance_models"] = request.assistance_models
    # Isolation evidence covers near-duplicates/groups across separate corpus versions.
    manifest["isolation_policy"] = "ID_DISJOINT_PLUS_HUMAN_GROUP_AND_CONTENT_REVIEW"
    manifest["assignment_sha256"] = store.digest(
        {k: v for k, v in manifest.items() if k != "assignment_sha256"}
    )
    recheck(root, source, rules, request, payload)
    if preview:
        target = store.digest({"protocol": rules.model_dump(), "allocation": manifest})
        path = protocol.base(root) / "previews" / ("preview_" + target[:32])
        documents = {"protocol.json": rules.model_dump(), "allocation.json": manifest}
        if path.exists():
            if store.bundle(path)[0] != documents:
                raise IngestionError("Allocation preview changed")
        else:
            store.publish(path, documents)
        return {
            "status": "ALLOCATION_PREVIEW_NOT_APPROVED",
            "target_sha256": target,
            "preview_id": path.name,
            "assigned": len(manifest["assignments"]),
            "orders": manifest["order_counts"],
            "test_labels_read": False,
        }
    protocol.freeze(root, rules, manifest, request.collection_authorization_ref)
    return {
        "status": "ALLOCATION_FROZEN",
        "mode": request.mode,
        "experiment_id": request.experiment_id,
        "assignment_sha256": manifest["assignment_sha256"],
        "assigned": len(manifest["assignments"]),
        "orders": manifest["order_counts"],
        "test_labels_read": False,
    }


def locked_allocation(root, request, payload, rules, frozen):
    identity = request.allocation_ref or request.experiment_id
    documents, _ = store.bundle(protocol.base(root) / "allocations" / store.identifier(identity))
    manifest, lock = documents["allocation.json"], documents["lock.json"]
    target = store.digest({"protocol": rules.model_dump(), "allocation": manifest})
    cases = [c for c in payload.cases if c.role == "EXPERIMENT_INDEPENDENT"]
    if (
        documents["protocol.json"] != rules.model_dump()
        or target != lock["target_sha256"]
        or any(
            (
                manifest["experiment_id"] != request.experiment_id,
                manifest["mode"] != request.mode,
                manifest["pool_sha256"]
                != store.digest(
                    [c.model_dump(mode="json") for c in sorted(cases, key=lambda c: c.case_id)]
                ),
                manifest["participants_sha256"]
                != store.digest(
                    [
                        p.model_dump()
                        for p in sorted(payload.participants, key=lambda p: p.participant_id)
                    ]
                ),
                manifest["dataset_binding_sha256"] != (store.digest(frozen) if frozen else None),
                manifest["source_id"] != request.source_id,
                manifest["assistance_models"] != request.assistance_models,
                manifest["implementation_sha256"] != protocol.implementation(),
                manifest["assignment_sha256"]
                != store.digest({k: v for k, v in manifest.items() if k != "assignment_sha256"}),
            )
        )
    ):
        raise IngestionBlocked(
            "Locked allocation, cases or protocol changed; no silent reassignment"
        )
    if request.mode != "SYNTHETIC_ENGINEERING_TEST":
        evidence = model_registry.authorize(
            root, lock["approval_ref"], "RESEARCH_ALLOCATION", target
        )
        if evidence != lock["authorization"]:
            raise IngestionBlocked("Allocation approval changed")
        earliest = [r.task_start_time for r in [*payload.observations, *payload.usability]]
        if earliest and datetime.fromisoformat(evidence["reviewed_at"]) >= min(earliest):
            raise IngestionBlocked("Allocation approval must precede collection")
    return manifest


def model_gate(root, registry, request, payload):
    mapped = request.assistance_models or {}
    models = set(mapped.values())
    if any(r.ai_suggestion_shown and r.model_versions != mapped for r in payload.observations):
        raise IngestionBlocked("Displayed assistance differs from frozen model references")
    if payload.participants and set(mapped) != {"topic", "sentiment", "severity"}:
        raise IngestionBlocked("Freeze three-task assistance references before collection")
    if request.mode == "SYNTHETIC_ENGINEERING_TEST":
        if models - {"synthetic_mock_v1"}:
            raise IngestionBlocked("Engineering smoke uses explicit mock model references only")
        return
    if request.mode == "HUMAN_FEASIBILITY_PILOT":
        if models - {"synthetic_mock_v1"}:
            raise IngestionBlocked(
                "Feasibility pilot permits only disclosed mock interface assistance"
            )
        return
    if any(
        r.condition == "AI_ASSISTED"
        and r.completion_status == "COMPLETED"
        and not r.ai_suggestion_shown
        for r in payload.observations
    ):
        raise IngestionBlocked("Completed research assisted tasks require recorded AI suggestions")
    if not models:
        return
    _, binding = baseline.development(root, registry, request.dataset_version)
    rq2.final_summary(root, registry, request.rq2_evaluation_id, binding)
    for identity in models:
        view = model_registry.view(root, registry, identity)
        record = view["record"]
        approved = [e for e in view["history"] if e["action"] == "RESEARCH_APPROVED"]
        if not approved or record["model"]["dataset"]["dataset_type"] != "RESEARCH":
            raise IngestionBlocked("Eligible research-approved AI model required")
        if (
            record["model"]["family"] == "phobert"
            and record["model"]["model_kind"] != "PRETRAINED_PHOBERT"
        ):
            raise IngestionBlocked(
                "Tiny random Transformer cannot assist real effectiveness experiment"
            )
        # A three-task suggestion requires documented evaluated models for all three tasks.
        # The reference identifies the existing STEP11 final experiment and approval authority.
        if record["model"]["dataset"]["dataset_version"] != request.dataset_version:
            raise IngestionBlocked("Assistance training dataset mismatch")
        if any(task != record["model"]["task"] for task, ref in mapped.items() if ref == identity):
            raise IngestionBlocked("Assistance model task mismatch")
        event = approved[-1]
        evidence = event["evaluation"]
        documents, checksum = store.bundle(
            model_registry.base(root) / "final_results" / evidence["id"]
        )
        if (
            evidence["id"] != request.rq2_evaluation_id
            or checksum != evidence["sha256"]
            or documents["report.json"]["selected_by_task"].get(record["model"]["task"]) != identity
        ):
            raise IngestionBlocked(
                "Documented validation-selected STEP11 model evaluation required"
            )
        authorization = model_registry.authorize(
            root,
            evidence["approval_ref"],
            "RESEARCH_APPROVAL",
            store.digest({"record": store.digest(record), "evaluation": checksum}),
        )
        for row in payload.observations:
            if not row.ai_suggestion_shown:
                continue
            for task, reference in row.model_versions.items():
                if reference == identity and (
                    task != record["model"]["task"]
                    or datetime.fromisoformat(authorization["reviewed_at"]) >= row.task_start_time
                ):
                    raise IngestionBlocked(
                        "Assistance task mapping or pre-collection approval mismatch"
                    )


def report(root, source, rq="all"):
    rules = protocol.load(root)
    request, payload, registry, frozen = validation.authorize_request(root, source, rules)
    case_gate(root, request, payload, registry, frozen)
    results = {}
    if rq in {"all", "rq1"}:
        selected = [c for c in payload.cases if c.role == "DESCRIPTIVE"]
        bases = {c.basis for c in selected}
        results["rq1"] = {
            basis: rq1.analyze([c for c in selected if c.basis == basis], basis)
            for basis in sorted(bases)
        } or {"status": "BLOCKED_ON_RESEARCH_DATA"}
    if rq in {"all", "rq2"}:
        if request.mode != "AUTHORIZED_RESEARCH":
            results["rq2"] = {
                "status": "BLOCKED_ON_RESEARCH_DATA",
                "models": [],
                "reason": "NO_GENUINE_RESEARCH_RUNS_IN_ENGINEERING_OR_FEASIBILITY_MODE",
            }
        else:
            _, binding = baseline.development(root, registry, request.dataset_version)
            results["rq2"] = rq2.final_summary(root, registry, request.rq2_evaluation_id, binding)
    if payload.observations or payload.usability or payload.questionnaires:
        allocation_manifest = locked_allocation(root, request, payload, rules, frozen)
        collection = validation.observations(
            payload, allocation_manifest, request.experiment_id, root
        )
        model_gate(root, registry, request, payload)
    else:
        allocation_manifest, collection = None, {"status": "BLOCKED_ON_EXPERIMENT"}
    if rq in {"all", "rq3"}:
        results["rq3"] = {
            "numerical_correctness": [
                {
                    "metric": c.metric,
                    "passed": c.expected == c.observed
                    if c.expected is None or c.observed is None
                    else abs(c.expected - c.observed) <= c.tolerance,
                }
                for c in payload.numerical_checks
            ],
            "alert_quality": rq3.alert_quality(
                [(w.eligible, w.triggered, w.reference_event) for w in payload.alert_windows]
            ),
            "human_usability": rq3.usability(payload.usability, payload.questionnaires),
        }
    if rq in {"all", "rq4"}:
        results["rq4"] = (
            rq4.analyze(payload, allocation_manifest, rules)
            if allocation_manifest
            else {"status": "BLOCKED_ON_EXPERIMENT"}
        )
        if request.mode == "HUMAN_FEASIBILITY_PILOT":
            results["rq4"]["status"] = "FEASIBILITY_ONLY_NO_EFFECTIVENESS_CLAIM"
    output = {
        "report_version": "research-report-1",
        "mode": request.mode,
        "notice": "SYNTHETIC DATA — ENGINEERING TEST ONLY"
        if request.mode == "SYNTHETIC_ENGINEERING_TEST"
        else "HUMAN FEASIBILITY ONLY — NO EFFECTIVENESS CLAIM"
        if request.mode == "HUMAN_FEASIBILITY_PILOT"
        else "AUTHORIZED CORPUS OBSERVATIONS — LIMITED GENERALIZABILITY",
        "protocol_version": rules.version,
        "protocol_sha256": request.protocol_sha256,
        "input_sha256": request.payload_sha256,
        "implementation_sha256": protocol.implementation(),
        "software": {"python": sys.version.split()[0], "pydantic": version("pydantic")},
        "collection": collection,
        "results": results,
        "test_labels_read": False,
        "scientific_conclusions_generated": False,
    }
    identity = (
        "report_" + store.digest({"request": request.model_dump(), "rq": rq, "output": output})[:32]
    )
    path = protocol.base(root) / "reports" / identity
    recheck(root, source, rules, request, payload)
    if path.exists():
        existing, _ = store.bundle(path)
        if existing != {"report.json": output}:
            raise IngestionError("Immutable research report changed")
    else:
        store.publish(path, {"report.json": output})
    return {"report_id": identity, **output}
