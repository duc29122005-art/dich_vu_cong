"""Current rights and consent checks precede protected collection-file reads."""

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime

from pfa.annotation import approval, pilot
from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import unique_object
from pfa.data import corpus
from pfa.data.official_io import IngestionBlocked, IngestionError, safe_path
from pfa.data.permissions import require_access
from pfa.data.registry import load_registry
from pfa.ml import model_registry
from pfa.research.protocol import base
from pfa.research.schemas import TEMPLATES, Assignment, Payload, Request


def unique(rows, key, message):
    values = [key(row) for row in rows]
    if len(values) != len(set(values)):
        raise IngestionError(message)


def consent(payload, mode, root=None):
    people = {p.participant_id: p for p in payload.participants}
    unique(payload.participants, lambda p: p.participant_id, "Duplicate participant")
    unique(
        payload.consent_events, lambda e: (e.participant_id, e.sequence), "Duplicate consent event"
    )
    histories = defaultdict(list)
    for event in payload.consent_events:
        if mode != "SYNTHETIC_ENGINEERING_TEST":
            if root is None:
                raise IngestionBlocked("Protected verified consent-event evidence required")
            model_registry.authorize(
                root,
                event.evidence_reference,
                "VERIFY_CONSENT_EVENT",
                store.digest(event.model_dump(mode="json")),
            )
        if (
            event.participant_id not in people
            or event.consent_reference != people[event.participant_id].consent_reference
        ):
            raise IngestionBlocked("Consent reference does not match participant")
        histories[event.participant_id].append(event)
    for person in people:
        history = sorted(histories[person], key=lambda e: e.sequence)
        if [e.sequence for e in history] != list(range(1, len(history) + 1)) or not history:
            raise IngestionBlocked("Complete consent-state history required")
        if any(e.occurred_at > datetime.now(UTC) for e in history) or any(
            a.occurred_at >= b.occurred_at for a, b in zip(history, history[1:])
        ):
            raise IngestionBlocked("Consent event chronology invalid")
        histories[person] = history
    for row in [*payload.observations, *payload.usability, *payload.questionnaires]:
        if (
            row.participant_id not in people
            or row.consent_reference != people[row.participant_id].consent_reference
        ):
            raise IngestionBlocked("Consent reference required for every observation")
        when = row.task_start_time if hasattr(row, "task_start_time") else row.collected_at
        end = getattr(row, "task_end_time", None)
        if when > datetime.now(UTC) or end and end > datetime.now(UTC):
            raise IngestionError("Future human observation timestamp")
        valid = [e for e in histories[row.participant_id] if e.occurred_at <= when]
        if any(
            e.state == "WITHDRAWN" and e.occurred_at >= when for e in histories[row.participant_id]
        ) or (
            not valid
            or valid[-1].state != "GRANTED"
            or histories[row.participant_id][-1].state != "GRANTED"
        ):
            raise IngestionBlocked("Consent must precede observation")
    for rows in (
        payload.cases,
        payload.participants,
        payload.consent_events,
        payload.observations,
        payload.usability,
        payload.questionnaires,
        payload.gold_references,
        payload.deviations,
    ):
        if any(row.mode != mode for row in rows):
            raise IngestionBlocked("Synthetic, feasibility and research modes cannot be mixed")


def observations(payload: Payload, manifest, experiment_id, root=None):
    consent(payload, manifest["mode"], root)
    unique(payload.cases, lambda c: c.case_id, "Duplicate case")
    unique(
        payload.observations,
        lambda o: o.assignment_id,
        "Duplicate or revised observation; explicit new design required",
    )
    unique(payload.usability, lambda o: (o.participant_id, o.task_id), "Repeated usability task")
    unique(payload.questionnaires, lambda q: q.participant_id, "Repeated questionnaire")
    unique(payload.alert_windows, lambda w: w.window_id, "Duplicate alert reference window")
    assignments = {
        a["assignment_id"]: Assignment.model_validate(a) for a in manifest["assignments"]
    }
    for deviation in payload.deviations:
        if deviation.experiment_id != experiment_id or (
            deviation.assignment_id is not None and deviation.assignment_id not in assignments
        ):
            raise IngestionBlocked("Deviation outside immutable experiment allocation")
    cases = {c.case_id: c for c in payload.cases}
    intervals = defaultdict(list)
    completed_assignments = set()
    for row in payload.observations:
        assigned = assignments.get(row.assignment_id)
        if (
            assigned is None
            or row.experiment_id != experiment_id
            or any(
                getattr(assigned, field) != getattr(row, field)
                for field in ("participant_id", "case_id", "condition", "condition_order")
            )
        ):
            raise IngestionBlocked("Observation outside immutable allocation")
        if (
            row.case_id not in cases
            or row.reference_gold_id != cases[row.case_id].reference_gold_id
        ):
            raise IngestionBlocked("Observation gold reference mismatch")
        if (
            row.task_start_time > datetime.now(UTC)
            or row.task_end_time
            and row.task_end_time > datetime.now(UTC)
        ):
            raise IngestionError("Future observation timestamp")
        intervals[row.participant_id].append((assigned, row))
        completed_assignments.add(row.assignment_id)
    for entries in intervals.values():
        ordered = sorted(entries, key=lambda item: (item[0].period, item[0].position))
        for (_, first), (_, second) in zip(ordered, ordered[1:]):
            if first.task_end_time is None or first.task_end_time > second.task_start_time:
                raise IngestionError("Experiment order violated or overlapping participant clocks")
    return {
        "assigned": len(assignments),
        "observed": len(completed_assignments),
        "missing_observations": len(set(assignments) - completed_assignments),
    }


def authorize_request(root, source, protocol, action="RESEARCH_PACKAGE"):
    request = Request.model_validate(store.read_json(safe_path(source), 65536))
    if request.protocol_sha256 != store.digest(protocol.model_dump()):
        raise IngestionBlocked("Research protocol version/checksum mismatch")
    registry = load_registry(root / "configs/dataset_sources.yaml")
    manifest = None
    if request.mode == "SYNTHETIC_ENGINEERING_TEST":
        store.require_synthetic(root)
        if request.source_id != "synthetic_demo":
            raise IngestionBlocked("Synthetic source required")
    else:
        if store.is_synthetic(root):
            raise IngestionBlocked("Synthetic session cannot authorize human observations")
        if request.mode == "AUTHORIZED_RESEARCH":
            try:
                require_access(root, registry, request.source_id, "internal_analysis")
                approval.require_taxonomy(root)
            except (PermissionError, ValueError, OSError):
                raise IngestionBlocked(
                    "Current source rights and taxonomy approval required"
                ) from None
            if not request.dataset_version:
                raise IngestionBlocked("BLOCKED_ON_RESEARCH_DATA")
            _, manifest = corpus._authorized_manifest(root, registry, request.dataset_version)
            if (
                manifest["dataset_type"] != "RESEARCH"
                or manifest["provenance"]["plan"]["source_id"] != request.source_id
            ):
                raise IngestionBlocked("Research dataset/source provenance mismatch")
            if set(request.case_membership) & set(manifest["membership"]["test"]):
                raise IngestionBlocked("Protected research holdout is inaccessible")
        elif request.source_id != "synthetic_demo" or request.dataset_version is not None:
            raise IngestionBlocked("Feasibility pilot currently supports invented materials only")
        target = store.digest(request.model_dump(exclude={"authorization_ref"}))
        model_registry.authorize(root, request.authorization_ref, action, target)
        if request.includes_human_participants:
            model_registry.authorize(
                root,
                request.ethics_authorization_ref,
                "PARTICIPANT_PROTOCOL",
                request.protocol_sha256,
            )
            access = model_registry.authorize(
                root,
                request.participant_access_ref,
                "HUMAN_PARTICIPANT_ACCESS",
                store.digest(
                    {
                        "protocol_sha256": request.protocol_sha256,
                        "source_id": request.source_id,
                        "dataset_version": request.dataset_version,
                        "mode": request.mode,
                        "case_membership": sorted(request.case_membership),
                    }
                ),
            )
            if request.mode == "AUTHORIZED_RESEARCH" and access["reviewer_role"] != "data_steward":
                raise IngestionBlocked("Provider/steward participant-display rights required")
    # Open only the exact currently authorized bundle; no user-controlled payload paths.
    documents, checksum = store.bundle(base(root) / "inputs" / request.payload_id)
    if checksum != request.payload_sha256 or set(documents) != {"payload.json"}:
        raise IngestionBlocked("Research input integrity/provenance mismatch")
    payload = Payload.model_validate(documents["payload.json"])
    if (
        request.mode != "SYNTHETIC_ENGINEERING_TEST"
        and bool(payload.participants) != request.includes_human_participants
    ):
        raise IngestionBlocked("Human-participant declaration and authorization mismatch")
    if request.mode != "SYNTHETIC_ENGINEERING_TEST" and request.includes_human_participants:
        collection_times = [r.task_start_time for r in [*payload.observations, *payload.usability]]
        collection_times.extend(q.collected_at for q in payload.questionnaires)
        if collection_times and any(
            datetime.fromisoformat(e["reviewed_at"]) >= min(collection_times)
            for e in (
                access,
                model_registry.authorize(
                    root,
                    request.ethics_authorization_ref,
                    "PARTICIPANT_PROTOCOL",
                    request.protocol_sha256,
                ),
            )
        ):
            raise IngestionBlocked(
                "Participant protocol and access rights must precede observations"
            )
    if sorted(c.case_id for c in payload.cases) != sorted(request.case_membership) or any(
        c.source_id != request.source_id for c in payload.cases
    ):
        raise IngestionBlocked("Research case membership/source mismatch")
    consent(payload, request.mode, root)
    return request, payload, registry, manifest


def independent_gold(root, registry, payload, frozen):
    """Read only disjoint pilot gold; reject protected membership before reading labels."""
    forbidden = {case for values in frozen["membership"].values() for case in values}
    refs = {g.case_id: g for g in payload.gold_references}
    unique(payload.gold_references, lambda g: g.case_id, "Repeated gold reference")
    resolved = {}
    for identity in sorted({g.pilot_id for g in refs.values()}):
        definition, _ = pilot.load_pilot(root, registry, identity)
        if set(definition.selected_ids) & forbidden:
            raise IngestionBlocked(
                "Independent experiment gold overlaps development or protected cases"
            )
        verified = pilot.verify_pilot(root, registry, identity)
        if not verified["human_gold"] or verified["dataset_type"] != "RESEARCH":
            raise IngestionBlocked("Independent human gold required")
        if {a.annotator_id for a in definition.plan.annotators.values()} & {
            p.participant_id for p in payload.participants
        }:
            raise IngestionBlocked("Experiment participant cannot establish own reference gold")
        documents, checksum = store.bundle(pilot.location(root, identity) / "adjudicated")
        for item in documents["resolved_records.json"]:
            resolved[item["feedback_id"]] = (identity, checksum, item)
    for case in payload.cases:
        if case.role != "EXPERIMENT_INDEPENDENT":
            continue
        ref, actual = refs.get(case.case_id), resolved.get(case.case_id)
        if ref is None or actual is None or case.basis != "adjudicated":
            raise IngestionBlocked("Experiment cases require independent adjudicated gold")
        identity, checksum, item = actual
        if (
            ref.reference_gold_id != case.reference_gold_id
            or ref.pilot_id != identity
            or ref.adjudicated_sha256 != checksum
            or item["source_id"] != case.source_id
            or item["dataset_version"] != case.source_version
            or any(
                getattr(case.labels, task) != item[task + "_label"]
                for task in ("topic", "sentiment", "severity")
            )
        ):
            raise IngestionBlocked("Independent gold label/provenance mismatch")


def validate_file(path, kind):
    schema = TEMPLATES[kind]
    path = safe_path(path)
    if (
        path.suffix.lower() not in {".csv", ".jsonl"}
        or not path.is_file()
        or path.stat().st_size > 20 * 1024**2
    ):
        raise IngestionError("Bounded CSV/JSONL collection file required")
    count = 0
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            if path.suffix.lower() == ".csv":
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames != list(schema.model_fields):
                    raise ValueError

                def records():
                    for row in reader:
                        parsed = {}
                        for field, value in row.items():
                            if field is None or value is None:
                                raise ValueError
                            try:
                                parsed[field] = (
                                    json.loads(value, object_pairs_hook=unique_object)
                                    if value
                                    else None
                                )
                            except json.JSONDecodeError:
                                parsed[field] = value
                        yield parsed
            else:

                def records():
                    for line in stream:
                        if line.strip():
                            yield json.loads(line, object_pairs_hook=unique_object)

            for record in records():
                count += 1
                if count > 20000:
                    raise ValueError
                value = schema.model_validate(record)
                if (
                    kind == "manual_observations"
                    and value.condition != "MANUAL_ONLY"
                    or kind == "assisted_observations"
                    and value.condition != "AI_ASSISTED"
                ):
                    raise ValueError
    except (ValueError, csv.Error, UnicodeError):
        raise IngestionError("Collection schema invalid; submitted values withheld") from None
    return {
        "status": "SCHEMA_VALID_ONLY",
        "records": count,
        "authorization_or_consent_established": False,
    }
