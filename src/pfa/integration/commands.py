"""Fixed safe CLI errors and explicit unavailable dependency/database exit codes."""


def run(root, action):
    try:
        from pfa.integration.contracts import load

        load(root)
        if not __debug__:
            raise ValueError("Engineering checks require Python assertions enabled")
        if action == "security-check":
            from pfa.integration.security_checks import scan

            result = scan(root)
            return result, 0 if result["status"] == "SECURITY_SCAN_PASS" else 2
        if action == "dependency-check":
            from pfa.integration.security_checks import dependencies

            return dependencies()
        if action == "performance":
            from pfa.integration.performance import smoke

            return smoke(root), 0
        from pfa.integration.smoke import smoke, smoke_postgres

        if action == "smoke-postgres":
            return smoke_postgres(root)
        return smoke(root), 0
    except ImportError:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "Install API, data, ML and dashboard dependencies",
        }, 4
    except Exception:
        # Drivers and validators can include credentials/text in exception repr.
        return {"status": "INTEGRATION_CHECK_FAILED", "submitted_values_withheld": True}, 2
