"""Opt-in local PostgreSQL verification in a fresh schema, never a database reset."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from pfa.data.official_io import IngestionBlocked
from pfa.db.models import Feedback, Prediction, ReviewEvent
from pfa.db.smoke import change, create, environment, exercise


def smoke(root, *, workflow=None):
    supplied = os.environ.get("TEST_DATABASE_URL")
    if not supplied:
        return {"POSTGRES_INTEGRATION": "NOT_VERIFIED", "reason": "TEST_DATABASE_URL required"}, 4
    engine = None
    schema = "pfa_test_" + uuid4().hex
    owned = False
    try:
        url = make_url(supplied)
        if (
            url.drivername != "postgresql+psycopg"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or not url.database
            or not url.database.endswith("_test")
            or url.query
        ):
            raise ValueError("Dedicated local PostgreSQL test database required")
        engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            owned = True
        with environment(root, postgres_url=supplied, schema=schema) as (
            client,
            database,
            headers,
            temporary_root,
        ):
            result = exercise(client, database, headers)
            second = create(client, headers["ADMIN"], fixture_id=1).json()
            barrier = Barrier(2)

            def claim(_):
                barrier.wait(timeout=10)
                return change(
                    client, headers["REVIEWER"], second["feedback_id"], "CLAIM", 1, "CLAIM"
                ).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sorted(pool.map(claim, range(2))) == [200, 409]
            assert (
                client.get("/api/v1/feedback?limit=1&offset=1", headers=headers["ANALYST"]).json()[
                    "total"
                ]
                == 2
            )
            with database.engine.connect() as connection:
                assert connection.dialect.name == "postgresql"
                assert (
                    connection.execute(text("SELECT count(*) FROM review_event")).scalar_one() == 7
                )
                assert (
                    connection.execute(
                        text(
                            "SELECT data_type FROM information_schema.columns "
                            "WHERE table_schema=current_schema() AND table_name='feedback' "
                            "AND column_name='created_at'"
                        )
                    ).scalar_one()
                    == "timestamp with time zone"
                )
            with database.sessions() as session:
                sample = session.scalar(select(Prediction))
                values = {c.key: getattr(sample, c.key) for c in Prediction.__table__.columns}
                for invalid in (
                    {"feedback_id": uuid4()},
                    {"model_version_id": uuid4()},
                    {"predicted_label": "invalid"},
                    {"calibrated": True},
                ):
                    try:
                        session.add(Prediction(**{**values, "prediction_id": uuid4(), **invalid}))
                        session.flush()
                    except IntegrityError:
                        session.rollback()
                    else:
                        raise AssertionError("PostgreSQL constraint not enforced")
                event = session.scalar(select(ReviewEvent))
                invalid_event = {
                    c.key: getattr(event, c.key) for c in ReviewEvent.__table__.columns
                }
                session.rollback()
                try:
                    with session.begin():
                        session.execute(
                            update(Feedback)
                            .where(Feedback.feedback_id == UUID(second["feedback_id"]))
                            .values(version=3, review_status="REVIEWED")
                        )
                        session.add(
                            ReviewEvent(
                                **{
                                    **invalid_event,
                                    "review_event_id": uuid4(),
                                    "operation_id": uuid4(),
                                    "feedback_id": uuid4(),
                                }
                            )
                        )
                        session.flush()
                except IntegrityError:
                    pass
                else:
                    raise AssertionError("Invalid audit transaction accepted")
                session.expire_all()
                assert session.get(Feedback, UUID(second["feedback_id"])).version == 2
            # Dispose pooled connections and reopen: data must survive connection lifecycle.
            database.close()
            database.validate()
            assert client.get("/api/v1/feedback", headers=headers["ANALYST"]).json()["total"] == 2
            if workflow is not None:
                result["integration"] = workflow(client, database, headers, temporary_root)
        return {
            "status": "DB_SMOKE_PASS_SYNTHETIC",
            "POSTGRES_INTEGRATION": "VERIFIED",
            "concurrent_claim_http": [200, 409],
            "schema_isolated": True,
            **result,
        }, 0
    except Exception:
        return {
            "POSTGRES_INTEGRATION": "NOT_VERIFIED",
            "reason": "Isolated PostgreSQL verification failed; credentials omitted",
        }, 2
    finally:
        if engine is not None:
            try:
                if owned:
                    # Remove only this newly created schema; never reset a database.
                    with engine.begin() as connection:
                        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            except Exception:
                raise IngestionBlocked(
                    "PostgreSQL test cleanup unverified; inspect owned test schemas"
                ) from None
            finally:
                engine.dispose()
