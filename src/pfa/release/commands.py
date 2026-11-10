"""Release CLI keeps secrets out of reports; no publishing, approvals or destructive commands."""


def run(root, args):
    try:
        action = args.release_action
        if action == "preflight":
            from pfa.release.preflight import preflight

            value = preflight(root, isolated=args.isolated)
            return value, 3 if value["status"] == "BLOCKED" else 0
        if action == "smoke":
            from pfa.release.smoke import smoke

            return smoke(root), 0
        if action == "audit":
            from pfa.release.audit import run as audit

            result, code = audit(root)
            if args.output:
                from pfa.annotation import pilot_store as store

                output = store.safe_path(root / args.output, root / "reports/releases")
                store.publish(output, {"audit.json": result})
            return result, code
        if action == "postgres-check":
            from pfa.integration.smoke import smoke_postgres

            result, code = smoke_postgres(root)
            return {
                **result,
                "POSTGRES_CURRENT_RUN": result["POSTGRES_INTEGRATION"],
                "POSTGRES_HISTORICAL": "VERIFIED_PER_STEP16_EVIDENCE",
            }, code
        if action in {"manifest", "verify"}:
            from pfa.release import manifest

            if action == "manifest":
                return manifest.publish(root, args.output), 0
            from pfa.annotation import pilot_store as store

            documents, _ = store.bundle(
                store.safe_path(root / args.manifest, root / "reports/releases")
            )
            return manifest.verify(root, documents["manifest.json"]), 0
        if action == "api":
            from pfa.release.demo import serve_api

            serve_api(root, args.port, args.seed)
            return {"status": "DEMO_API_STOPPED", "temporary_storage_cleaned": True}, 0
        if action == "dashboard":
            from pfa.release.demo import serve_dashboard

            code = serve_dashboard(root, args.port)
            return {"status": "DEMO_DASHBOARD_STOPPED"}, 0 if code == 0 else 2
        raise ValueError("Unknown release command")
    except ImportError:
        return {"status": "BLOCKED", "reason": "INSTALL_LOCKED_RELEASE_DEPENDENCIES"}, 4
    except KeyboardInterrupt:
        return {"status": "LOCAL_DEMO_STOPPED"}, 0
    except Exception:
        return {
            "status": "BLOCKED",
            "reason": "INVALID_CONFIGURATION_OR_FAILED_RELEASE_CHECK",
            "submitted_values_withheld": True,
        }, 2
