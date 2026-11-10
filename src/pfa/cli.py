"""Offline environment diagnostics; never prints configuration values."""

import argparse
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryFile

from pydantic import ValidationError

from pfa.annotation import approval, pilot, pilot_smoke
from pfa.annotation import io as annotation_io
from pfa.annotation.taxonomy import CHECKSUM, load_taxonomy
from pfa.core.config import Settings
from pfa.data import acquisition, benchmark, corpus, corpus_smoke, official, profiling
from pfa.data.adapters.uit_vsfc import BenchmarkError
from pfa.data.assessment import assess
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.official_schema import Feedback
from pfa.data.permissions import Decision, current_decision, permitted_scopes, record_decision
from pfa.data.registry import Source, load_registry
from pfa.data.splitting import SplitConfig


def doctor() -> int:
    """Check the installed package and workspace; return nonzero on critical failure."""
    failed = False

    def report(ok: bool, label: str) -> None:
        nonlocal failed
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        failed |= not ok

    report(sys.version_info[:2] == (3, 11), "Python 3.11")
    for package in ("public-feedback-ai", "pydantic-settings"):
        try:
            version(package)
        except PackageNotFoundError:
            report(False, f"Installed package: {package}")
        else:
            report(True, f"Installed package: {package}")
    try:
        settings = Settings()
    except (ValueError, OSError):
        report(False, "Configuration/environment invalid; check PFA_ variables and .env")
        return 1
    report(True, "Configuration and environment valid")
    for directory in settings.required_directories:
        label = str(directory.relative_to(settings.project_root))
        report(directory.is_dir(), f"Directory: {label}")
        if not directory.is_dir():
            continue
        try:
            if not os.access(directory, os.R_OK | os.X_OK):
                raise PermissionError
            with os.scandir(directory):
                pass
            with TemporaryFile(dir=directory) as probe:
                probe.write(b"pfa permission check")
                probe.flush()
        except OSError:
            report(False, f"Read/write permissions: {label}")
        else:
            report(True, f"Read/write permissions: {label}")
    if not (settings.project_root / ".env").is_file():
        print("WARN No .env file; defaults and environment variables are used")
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(prog="pfa")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    release = commands.add_parser("release").add_subparsers(dest="release_action", required=True)
    release.add_parser("preflight").add_argument("--isolated", action="store_true")
    release.add_parser("smoke")
    release.add_parser("postgres-check")
    release.add_parser("audit").add_argument("--output", type=Path)
    release.add_parser("manifest").add_argument("--output", type=Path, required=True)
    release.add_parser("verify").add_argument("--manifest", type=Path, required=True)
    release_api = release.add_parser("api")
    release_api.add_argument("--port", type=int, default=8000)
    release_api.add_argument("--seed", type=int)
    release.add_parser("dashboard").add_argument("--port", type=int, default=8501)
    integration = commands.add_parser("integration").add_subparsers(
        dest="integration_action", required=True
    )
    for operation in (
        "smoke",
        "smoke-postgres",
        "security-check",
        "dependency-check",
        "performance",
    ):
        integration.add_parser(operation)
    research = commands.add_parser("research").add_subparsers(dest="research_action", required=True)
    for operation in ("status", "protocol-check", "smoke"):
        research.add_parser(operation)
    research.add_parser("templates").add_argument("--output", type=Path)
    research_report = research.add_parser("report")
    research_report.add_argument("--rq", choices=["all", "rq1", "rq2", "rq3", "rq4"], default="all")
    research_report.add_argument("--source", type=Path, required=True)
    research_assignments = research.add_parser("assignments")
    research_assignments.add_argument("--source", type=Path, required=True)
    research_assignments.add_argument("--preview", action="store_true")
    research_validation = research.add_parser("validate")
    research_validation.add_argument(
        "--kind",
        choices=[
            "participants",
            "assignments",
            "manual_observations",
            "assisted_observations",
            "dashboard_tasks",
            "questionnaire",
            "gold_references",
            "deviations",
            "consent_events",
        ],
        required=True,
    )
    research_validation.add_argument("--input", type=Path, required=True)
    analytics = commands.add_parser("analytics").add_subparsers(
        dest="analytics_action", required=True
    )
    analytics.add_parser("smoke")
    analytics.add_parser("seed-demo")
    db = commands.add_parser("db").add_subparsers(dest="db_action", required=True)
    for operation in ("status", "smoke", "check-migrations", "smoke-postgres"):
        db.add_parser(operation)
    api = commands.add_parser("api").add_subparsers(dest="api_action", required=True)
    api.add_parser("smoke")
    api.add_parser("status")
    serve = api.add_parser("serve")
    serve.add_argument("--host", choices=["127.0.0.1", "localhost", "::1"], default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    ml = commands.add_parser("ml").add_subparsers(dest="ml_action", required=True)
    ml.add_parser("baseline-smoke")
    for operation in ("train-baselines", "compare"):
        command = ml.add_parser(operation)
        command.add_argument("--dataset", required=True)
        command.add_argument(
            "--task",
            choices=["topic", "sentiment", "severity"],
            required=operation == "train-baselines",
        )
        if operation == "train-baselines":
            command.add_argument("--seed", type=int, default=42)
            command.add_argument("--config", type=Path)
    ml.add_parser("inspect").add_argument("--run-id", required=True)
    ml.add_parser("evaluation-smoke")
    evaluate = ml.add_parser("evaluate")
    evaluate.add_argument("--dataset", required=True)
    evaluate.add_argument("--split", choices=["test"], required=True)
    evaluate.add_argument("--all", action="store_true", required=True)
    evaluate.add_argument("--experiment-id")
    evaluate.add_argument("--approval-ref")
    evaluate.add_argument("--evaluation-ref")
    evaluate.add_argument("--segmenters", type=Path)
    prepare = ml.add_parser("prepare-evaluation")
    prepare.add_argument("--dataset", required=True)
    prepare.add_argument("--run-id", action="append", required=True)
    prepare.add_argument("--trust-refs", type=Path)
    prepare.add_argument("--segmenters", type=Path)
    prepare.add_argument("--config", type=Path)
    lock = ml.add_parser("lock-protocol")
    lock.add_argument("--experiment-id", required=True)
    lock.add_argument("--approval-ref", required=True)
    model_commands = ml.add_parser("registry").add_subparsers(dest="registry_action", required=True)
    model_commands.add_parser("list")
    for operation in ("inspect", "promote", "register", "approve"):
        command = model_commands.add_parser(operation)
        command.add_argument("--run-id", required=True)
        if operation in {"promote", "approve"}:
            command.add_argument("--approval-ref")
        if operation == "approve":
            command.add_argument("--evaluation-id", required=True)
        if operation == "register":
            command.add_argument("--family", choices=["lr", "svm", "phobert"], required=True)
    rollback = model_commands.add_parser("rollback")
    rollback.add_argument("--task", choices=["topic", "sentiment", "severity"], required=True)
    rollback.add_argument("--to-run-id", required=True)
    rollback.add_argument("--approval-ref")
    ml.add_parser("phobert-smoke")
    ml.add_parser("phobert-inspect").add_argument("--run-id", required=True)
    readiness_command = ml.add_parser("phobert-readiness")
    readiness_command.add_argument("--config", type=Path)
    phobert_command = ml.add_parser("train-phobert")
    phobert_command.add_argument("--dataset", required=True)
    phobert_command.add_argument(
        "--task", choices=["topic", "sentiment", "severity"], required=True
    )
    phobert_command.add_argument("--seed", type=int, default=42)
    phobert_command.add_argument("--config", type=Path)
    phobert_command.add_argument("--device", choices=["cpu", "cuda", "auto"])
    phobert_command.add_argument("--resume-run")
    annotation = commands.add_parser("annotation").add_subparsers(
        dest="annotation_action", required=True
    )
    taxonomy_commands = annotation.add_parser("taxonomy").add_subparsers(
        dest="taxonomy_action", required=True
    )
    taxonomy_commands.add_parser("show")
    taxonomy_commands.add_parser("record").add_argument("--decision-ref", required=True)
    annotation.add_parser("pilot-smoke")
    sampling = annotation.add_parser("sample-pilot")
    sampling.add_argument("--source", required=True)
    sampling.add_argument("--n", type=int, default=200)
    sampling.add_argument("--seed", type=int, default=42)
    sampling.add_argument("--pilot", default="pilot_v1")
    sampling.add_argument("--plan-ref", default="pilot_v1")
    for operation in ("export", "import", "agreement", "adjudicate", "verify-pilot"):
        command = annotation.add_parser(operation)
        command.add_argument("--pilot", default="pilot_v1")
        if operation in {"export", "import"}:
            command.add_argument("--annotator", required=True, choices=["A", "B"])
        if operation == "import":
            command.add_argument("--input", required=True, type=Path)
            command.add_argument("--receipt-ref")
            command.add_argument("--revision", type=int, default=1)
        if operation == "adjudicate":
            command.add_argument("--decision-ref")
    annotation.add_parser("template").add_argument("--output", type=Path, required=True)
    annotation_validation = annotation.add_parser("validate")
    annotation_validation.add_argument("--input", type=Path, required=True)
    annotation_validation.add_argument("--schema-only", action="store_true")
    dataset = commands.add_parser("dataset").add_subparsers(dest="action", required=True)
    dataset.add_parser("sources")
    acquisition_commands = dataset.add_parser("acquisition").add_subparsers(
        dest="acquisition_action", required=True
    )
    acquisition_commands.add_parser("smoke")
    for operation in ("status", "request-pack", "preflight", "receive"):
        command = acquisition_commands.add_parser(operation)
        command.add_argument("--source", required=True)
        if operation == "request-pack":
            command.add_argument("--output", required=True, type=Path)
        elif operation == "preflight":
            command.add_argument(
                "--scope",
                default="internal_analysis",
                choices=["internal_analysis", "training", "publication", "software_tests"],
            )
        elif operation == "receive":
            command.add_argument("--input", required=True, type=Path)
            command.add_argument("--approval-ref", required=True)
            command.add_argument("--handoff-id", required=True)
    acquisition_commands.add_parser("verify").add_argument("--receipt-id", required=True)
    event_command = acquisition_commands.add_parser("record-event")
    event_command.add_argument("--source", required=True)
    event_command.add_argument("--event-ref", required=True)
    dataset.add_parser("split-smoke")
    build_command = dataset.add_parser("build")
    build_command.add_argument("--version", required=True)
    build_command.add_argument("--seed", type=int, default=42)
    build_command.add_argument("--config", type=Path)
    build_command.add_argument("--preview", action="store_true")
    dataset.add_parser("check-leakage").add_argument("--version", required=True)
    for operation in ("profile", "preprocess", "audit-privacy"):
        command = dataset.add_parser(operation)
        command.add_argument("--source", required=True)
        command.add_argument("--dataset-version")
        command.add_argument("--config", type=Path)
    assessment = dataset.add_parser("assess")
    assessment.add_argument("--source", required=True)
    approval_command = dataset.add_parser("approve")
    approval_command.add_argument("--source", required=True)
    approval_command.add_argument("--approval-ref", required=True)
    benchmarks = dataset.add_parser("benchmark").add_subparsers(dest="operation", required=True)
    for operation in ("inspect", "fetch", "verify"):
        command = benchmarks.add_parser(operation)
        command.add_argument("--source", required=True, choices=["uit_vsfc"])
        if operation in {"inspect", "fetch"}:
            command.add_argument("--approval-ref", required=operation == "fetch")
            command.add_argument("--revision", default=benchmark.DEFAULT_REVISION)
        if operation == "inspect":
            command.add_argument("--remote", action="store_true")
    officials = dataset.add_parser("official").add_subparsers(
        dest="official_operation", required=True
    )
    officials.add_parser("schema")
    smoke = officials.add_parser("smoke")
    smoke.add_argument("--fixture", type=Path, required=True)
    import_command = officials.add_parser("import")
    import_command.add_argument("--source", required=True)
    import_command.add_argument("--input", type=Path, required=True)
    import_command.add_argument("--approval-ref", required=True)
    import_command.add_argument("--mode", choices=["preview", "commit"], required=True)
    import_command.add_argument("--options", type=Path)
    import_command.add_argument("--review-ref")
    import_command.add_argument("--receipt-id")
    officials.add_parser("verify").add_argument("--dataset-version", required=True)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    try:
        settings = Settings()
        root = settings.project_root
        if args.command == "release":
            from pfa.release.commands import run as release_run

            result, code = release_run(root, args)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return code
        if args.command == "integration":
            from pfa.integration.commands import run as integration_run

            result, code = integration_run(root, args.integration_action)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return code
        if args.command == "research":
            from pfa.research.commands import run as research_run

            result, code = research_run(root, args)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return code
        if args.command == "analytics":
            if args.analytics_action == "smoke":
                from pfa.analytics.smoke import smoke as analytics_smoke

                result = analytics_smoke(root)
            else:
                from pfa.analytics.fixtures import seed
                from pfa.api.settings import ApiSettings
                from pfa.db.session import Database, DbSettings

                api_settings = ApiSettings()
                if api_settings.mode != "DEMO_ONLY" or settings.environment == "production":
                    raise IngestionBlocked("Explicit local DEMO_ONLY mode required")
                database = Database(root, DbSettings())
                try:
                    result = seed(database)
                finally:
                    database.close()
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        if args.command == "db":
            try:
                from pfa.db.commands import run
            except ImportError:
                print("NOT_AVAILABLE: install optional api dependencies")
                return 4
            result, code = run(root, args.db_action)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return code
        if args.command == "api":
            try:
                from fastapi.testclient import TestClient

                from pfa.api.app_factory import create_app
                from pfa.api.settings import ApiSettings
                from pfa.api.smoke import smoke
            except ImportError:
                print("NOT_AVAILABLE: install the optional api dependencies")
                return 4
            if args.api_action == "smoke":
                result = smoke(root)
            elif args.api_action == "status":
                app = create_app(root=root)
                with TestClient(
                    app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
                ) as client:
                    response = client.get("/health/ready")
                    result = response.json()
                print(json.dumps(result, ensure_ascii=True, indent=2))
                return 0 if result["prediction_ready"] else 3
            else:
                import uvicorn

                from pfa.core.logging import configure_logging

                configure_logging()
                config = ApiSettings(
                    environment=settings.environment, host=args.host, port=args.port
                )
                app = create_app(config, root=root)
                uvicorn.run(
                    app,
                    host=config.host,
                    port=config.port,
                    access_log=False,
                    proxy_headers=False,
                    workers=1,
                )
                return 0
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        if args.command == "ml":
            # Lazy imports keep the existing non-ML CLI usable without scikit-learn.
            from pfa.ml import baseline, baseline_smoke

            registry = load_registry(root / "configs/dataset_sources.yaml")
            if args.ml_action in {
                "evaluation-smoke",
                "evaluate",
                "registry",
                "prepare-evaluation",
                "lock-protocol",
            } or (args.ml_action == "compare" and args.task is None):
                from pfa.ml import evaluation, evaluation_policy, evaluation_smoke, model_registry

                if args.ml_action == "evaluation-smoke":
                    result = evaluation_smoke.smoke(registry)
                elif args.ml_action == "compare":
                    result = evaluation.comparison(root, registry, args.dataset)
                elif args.ml_action == "evaluate":
                    result = evaluation.final_evaluate(
                        root,
                        registry,
                        args.dataset,
                        args.experiment_id,
                        args.approval_ref,
                        args.evaluation_ref,
                        corpus.store.read_json(args.segmenters) if args.segmenters else None,
                    )
                elif args.ml_action == "prepare-evaluation":
                    result = evaluation.prepare(
                        root,
                        registry,
                        args.dataset,
                        args.run_id,
                        protocol=evaluation_policy.Protocol.model_validate(
                            corpus.store.read_json(args.config)
                        )
                        if args.config
                        else None,
                        trust_refs=corpus.store.read_json(args.trust_refs)
                        if args.trust_refs
                        else None,
                        segmenter_configs=corpus.store.read_json(args.segmenters)
                        if args.segmenters
                        else None,
                    )
                elif args.ml_action == "lock-protocol":
                    result = evaluation.lock(root, registry, args.experiment_id, args.approval_ref)
                elif args.registry_action == "list":
                    result = {
                        "models": [
                            model_registry.view(root, registry, r["run_id"])
                            for r in model_registry.entries(root, registry)
                        ],
                        "namespace": "RESEARCH",
                        "research_comparison": "BLOCKED_WITHOUT_APPROVED_EXPERIMENTS",
                    }
                elif args.registry_action == "register":
                    result = model_registry.register(root, registry, args.run_id, args.family)
                elif args.registry_action == "inspect":
                    result = model_registry.view(root, registry, args.run_id)
                elif args.registry_action == "promote":
                    result = model_registry.activate(
                        root, registry, args.run_id, approval_ref=args.approval_ref
                    )
                elif args.registry_action == "approve":
                    result = model_registry.research_approve(
                        root, registry, args.run_id, args.evaluation_id, args.approval_ref
                    )
                else:
                    record = model_registry.inspect(root, registry, args.to_run_id)
                    if record["model"]["task"] != args.task:
                        raise IngestionError("Rollback task mismatch")
                    result = model_registry.activate(
                        root,
                        registry,
                        args.to_run_id,
                        approval_ref=args.approval_ref,
                        rollback=True,
                    )
                print(json.dumps(result, ensure_ascii=True, indent=2))
                return 0
            if args.ml_action in {
                "phobert-smoke",
                "train-phobert",
                "phobert-inspect",
                "phobert-readiness",
            }:
                from pfa.ml import phobert, phobert_smoke

                if args.ml_action == "phobert-smoke":
                    result = phobert_smoke.smoke(registry)
                elif args.ml_action == "phobert-inspect":
                    result = phobert.inspect(root, registry, args.run_id)
                else:
                    config = (
                        phobert.PhobertConfig.model_validate(corpus.store.read_json(args.config))
                        if args.config
                        else phobert.PhobertConfig()
                    )
                    if args.ml_action == "phobert-readiness":
                        result = phobert.readiness(root, config)
                    else:
                        if args.device:
                            config = config.model_copy(update={"device": args.device})
                        result = phobert.train(
                            root,
                            registry,
                            args.dataset,
                            args.task,
                            args.seed,
                            config,
                            args.resume_run,
                        )
                print(json.dumps(result, ensure_ascii=True, indent=2))
                return 3 if result.get("status") == "BLOCKED" else 0
            elif args.ml_action == "baseline-smoke":
                result = baseline_smoke.smoke(registry)
            elif args.ml_action == "inspect":
                result = baseline.inspect(root, registry, args.run_id)
            elif args.ml_action == "compare":
                result = baseline.compare(root, registry, args.dataset, args.task)
            else:
                config = (
                    baseline.BaselineConfig.model_validate(corpus.store.read_json(args.config))
                    if args.config
                    else baseline.BaselineConfig()
                )
                result = baseline.train(root, registry, args.dataset, args.task, args.seed, config)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        if args.command == "annotation":
            if args.annotation_action == "taxonomy":
                if args.taxonomy_action == "record":
                    result = approval.record_taxonomy(root, args.decision_ref)
                else:
                    taxonomy = load_taxonomy(root)
                    result = {"taxonomy": taxonomy.model_dump(), "checksum": CHECKSUM}
            elif args.annotation_action == "template":
                result = annotation_io.template(root, args.output)
            elif args.annotation_action == "validate":
                registry = load_registry(root / "configs/dataset_sources.yaml")
                result = annotation_io.validate(root, registry, args.input, args.schema_only)
            else:
                registry = load_registry(root / "configs/dataset_sources.yaml")
                action = args.annotation_action
                if action == "pilot-smoke":
                    result = pilot_smoke.smoke(root, registry)
                elif action == "sample-pilot":
                    # Human taxonomy/data gates precede secret-key parsing and dataset reads.
                    approval.require_taxonomy(root)
                    decision = current_decision(root, registry, args.source)
                    official.authorize(
                        root, registry, args.source, decision.approval_ref if decision else ""
                    )
                    try:
                        key = bytes.fromhex(settings.fingerprint_key.get_secret_value())
                    except (ValueError, AttributeError):
                        raise IngestionError("Protected PFA_FINGERPRINT_KEY required") from None
                    result = pilot.sample_pilot(
                        root,
                        registry,
                        args.source,
                        args.n,
                        args.seed,
                        args.pilot,
                        args.plan_ref,
                        key,
                    )
                elif action == "export":
                    result = pilot.export_assignment(root, registry, args.pilot, args.annotator)
                elif action == "import":
                    reference = (
                        args.receipt_ref
                        or f"{args.pilot}_{args.annotator.lower()}_r{args.revision}"
                    )
                    result = pilot.import_submission(
                        root,
                        registry,
                        args.pilot,
                        args.annotator,
                        args.input,
                        reference,
                        args.revision,
                    )
                elif action == "agreement":
                    result, _ = pilot.agreement_report(root, registry, args.pilot)
                elif action == "verify-pilot":
                    result = pilot.verify_pilot(root, registry, args.pilot)
                elif args.decision_ref:
                    result = pilot.adjudicate(root, registry, args.pilot, args.decision_ref)
                else:
                    result = pilot.export_review(root, registry, args.pilot)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            if result.get("status") == "NOT_AVAILABLE":
                return 4
            return 2 if result.get("status") == "FAIL" else 0
        registry = load_registry(root / "configs/dataset_sources.yaml")
        if args.action == "acquisition":
            operation = args.acquisition_action
            if operation == "status":
                result = acquisition.status(root, registry, args.source)
            elif operation == "request-pack":
                result = acquisition.request_pack(root, registry, args.source, args.output)
            elif operation == "preflight":
                result = acquisition.preflight(root, registry, args.source, args.scope)
            elif operation == "receive":
                result = acquisition.receive(
                    root, registry, args.source, args.input, args.approval_ref, args.handoff_id
                )
            elif operation == "verify":
                result = acquisition.verify(root, registry, args.receipt_id)
                # Payload locations are private handoff metadata, not normal CLI output.
                result = {key: value for key, value in result.items() if key != "input"}
            elif operation == "record-event":
                result = acquisition.events.record(root, registry, args.source, args.event_ref)
            else:
                result = acquisition.smoke(root, registry)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 3 if result.get("status") == "BLOCKED_PERMISSION" else 0
        if args.action in {"build", "check-leakage", "split-smoke"}:
            if args.action == "split-smoke":
                result = corpus_smoke.smoke(registry)
            elif args.action == "check-leakage":
                result = corpus.verify(root, registry, args.version)
            else:
                approval.require_taxonomy(root)
                config = (
                    SplitConfig.model_validate(corpus.store.read_json(args.config))
                    if args.config
                    else SplitConfig()
                )
                try:
                    key = bytes.fromhex(settings.fingerprint_key.get_secret_value())
                except (ValueError, AttributeError):
                    raise IngestionError("Protected PFA_FINGERPRINT_KEY required") from None
                result = corpus.build(
                    root, registry, args.version, args.seed, config, key, args.preview
                )
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2 if result.get("status") == "FAIL" else 0
        if args.action in {"profile", "preprocess", "audit-privacy"}:
            key = None
            if args.source != "synthetic_demo":
                # Authorization precedes secret/config/manifest processing.
                decision = current_decision(root, registry, args.source)
                official.authorize(
                    root, registry, args.source, decision.approval_ref if decision else ""
                )
                try:
                    key = bytes.fromhex(settings.fingerprint_key.get_secret_value())
                except (ValueError, AttributeError):
                    raise IngestionError("Set a protected PFA_FINGERPRINT_KEY") from None
            report, path = profiling.run_audit(
                root, registry, args.source, key, args.dataset_version, args.config
            )
            print(
                json.dumps(
                    {
                        "action": args.action,
                        "report_directory": str(path.relative_to(root)),
                        "dataset_type": report.dataset_type,
                        "record_count": report.record_count,
                        "valid_count": report.valid_count,
                        "invalid_count": report.invalid_count,
                        "privacy_statistics": report.privacy_statistics,
                        "duplicate_statistics": report.duplicate_statistics,
                        "transformations": report.transformation_statistics["changes"],
                        "status": report.overall_quality_status,
                        "publication_eligible": report.publication_eligible,
                    },
                    indent=2,
                )
            )
            return {"PASS": 0, "WARN": 0, "FAIL": 2, "BLOCKED_PERMISSION": 3, "NOT_AVAILABLE": 4}[
                report.overall_quality_status
            ]
        if args.action == "official":
            if args.official_operation == "schema":
                result = Feedback.model_json_schema()
            elif args.official_operation == "smoke":
                result = official.smoke(args.fixture, registry)
            elif args.official_operation == "verify":
                result = official.verify(root, registry, args.dataset_version)
            else:
                # Permission must precede input/options reads and secret-key validation.
                official.authorize(
                    root, registry, args.source, args.approval_ref, commit=args.mode == "commit"
                )
                try:
                    key = bytes.fromhex(settings.fingerprint_key.get_secret_value())
                except (ValueError, AttributeError):
                    raise IngestionError(
                        "Set a protected PFA_FINGERPRINT_KEY with 64 random hex digits"
                    ) from None
                if args.receipt_id:
                    received = acquisition.verify(root, registry, args.receipt_id)
                    expected = root / received["input"]
                    supplied = args.input if args.input.is_absolute() else root / args.input
                    if (
                        received["step04_handoff"] != "READY"
                        or (received["source_id"], received["approval_ref"])
                        != (args.source, args.approval_ref)
                        or acquisition.safe_path(supplied, root)
                        != acquisition.safe_path(expected, root)
                    ):
                        raise IngestionBlocked(
                            "Verified acquisition receipt does not match official import"
                        )
                    args.input = expected
                result = official.ingest(
                    root,
                    registry,
                    args.source,
                    args.input,
                    args.approval_ref,
                    key,
                    args.mode,
                    options_path=args.options,
                    review_ref=args.review_ref,
                )
            print(json.dumps(result, indent=2, ensure_ascii=True))
        elif args.action == "benchmark":
            if args.operation == "inspect":
                result = benchmark.inspect_local(root, registry)
                if args.remote:
                    if not args.approval_ref:
                        raise benchmark.BenchmarkPermissionError(
                            "BLOCKED_PERMISSION: remote inspection requires "
                            "an audited approval reference"
                        )
                    result["remote_metadata"] = benchmark.discover(
                        root, registry, args.approval_ref, args.revision
                    )
            elif args.operation == "fetch":
                result = benchmark.fetch(root, registry, args.approval_ref, args.revision)
            else:
                result = benchmark.verify_local(root, registry)
            print(json.dumps(result, indent=2, ensure_ascii=True))
        elif args.action == "sources":
            for source in registry.sources:
                scopes = permitted_scopes(root, registry, source)
                print(
                    f"{source.source_id} | {source.dataset_role} | "
                    f"declared={source.permission_status} | "
                    f"effective_scope={','.join(scopes) or 'NONE'}"
                )
        elif args.action == "assess":
            print(json.dumps(assess(root, registry, args.source), indent=2))
        else:
            decision = record_decision(root, registry, args.source, args.approval_ref)
            print(
                f"Recorded human decision: {decision.decision}; "
                f"scope={','.join(decision.allowed_scope) or 'NONE'}. "
                "This command does not establish legal authorization."
            )
    except IngestionBlocked as error:
        print(str(error))
        return 3
    except IngestionError as error:
        print(str(error))
        return 4 if str(error).startswith("NOT_AVAILABLE") else 2
    except benchmark.BenchmarkPermissionError as error:
        print(str(error))
        return 3
    except BenchmarkError as error:
        print(str(error))
        return 4 if str(error).startswith("NOT_AVAILABLE") else 2
    except PermissionError:
        print("FAIL Permission gate: existing verified evidence and allowed scope required")
        return 3
    except (ValueError, OSError) as error:
        # Never echo arbitrary input or user-supplied dictionary keys.
        if isinstance(error, ValidationError):
            fields = (
                set(Source.model_fields) | set(Decision.model_fields) | {"sources", "decisions"}
            )
            locations = [
                ".".join(
                    str(part) if isinstance(part, int) or part in fields else "<field>"
                    for part in item["loc"]
                )
                or "record"
                for item in error.errors(include_input=False)
            ]
            print("FAIL Invalid metadata fields: " + ", ".join(locations))
        else:
            print("FAIL Dataset ID, registry, evidence, or audit history invalid/unavailable")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
