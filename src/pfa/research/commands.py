"""Offline CLI dispatch with fixed privacy-safe errors and explicit governance exits."""

from pfa.annotation import pilot_store as store
from pfa.data.official_io import IngestionBlocked
from pfa.research import protocol, reporting, validation
from pfa.research.schemas import TEMPLATES


def run(root, args):
    try:
        action = args.research_action
        if action == "smoke":
            from pfa.research.smoke import smoke

            return smoke(root), 0
        if action == "status":
            return reporting.status(root), 0
        if action == "protocol-check":
            rules = protocol.load(root)
            return {
                "status": "PROTOCOL_CHECK_PASS",
                "human_approval": "PENDING",
                "protocol_version": rules.version,
                "protocol_sha256": store.digest(rules.model_dump()),
                "step11_config_sha256": rules.evaluation_config_sha256,
                "step11_document_sha256": rules.evaluation_document_sha256,
                "test_labels_read": False,
            }, 0
        if action == "templates":
            if args.output is not None:
                return protocol.templates(args.output), 0
            directory = root / "templates/research"
            for name in TEMPLATES:
                for suffix in (".csv", ".jsonl"):
                    if validation.validate_file(directory / (name + suffix), name)["records"]:
                        raise ValueError("Official templates must remain blank")
            return {
                "status": "BLANK_TEMPLATES_VERIFIED",
                "schemas": sorted(TEMPLATES),
                "records": 0,
            }, 0
        if action == "validate":
            return validation.validate_file(args.input, args.kind), 0
        if action == "assignments":
            return reporting.allocation(root, args.source, getattr(args, "preview", False)), 0
        output = reporting.report(root, args.source, args.rq)

        def blocked(value):
            if isinstance(value, dict):
                return value.get("status", "").startswith(("BLOCKED", "INSUFFICIENT")) or any(
                    blocked(v) for v in value.values()
                )
            if isinstance(value, list):
                return any(blocked(v) for v in value)
            return False

        return output, 3 if blocked(output["results"]) else 0
    except IngestionBlocked:
        return {
            "status": "BLOCKED_ON_EXPERIMENT"
            if getattr(args, "rq", "all") == "rq4" or args.research_action == "assignments"
            else "BLOCKED_ON_RESEARCH_DATA",
            "reason": "CURRENT_PERMISSION_PROTOCOL_PROVENANCE_CONSENT_AND_GOLD_EVIDENCE_REQUIRED",
            "test_labels_read": False,
        }, 3
    except (ValueError, OSError, KeyError, TypeError):
        return {
            "status": "INVALID_RESEARCH_INPUT",
            "reason": "MISSING_OR_INVALID_SCHEMA_INTEGRITY_OR_BINDING",
            "submitted_values_withheld": True,
        }, 2
