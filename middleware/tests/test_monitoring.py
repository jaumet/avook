import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.monitoring import (
    InMemoryLogPublisher,
    RequestMonitoringMiddleware,
    Telemetry,
    configure_logging,
    override_publisher,
)


def test_request_monitoring_records_metrics_and_logs():
    telemetry = Telemetry(app_name="test-app")
    publisher = InMemoryLogPublisher()

    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level
    previous_publisher = override_publisher(publisher)

    try:
        configure_logging(app_name="test-monitoring", publisher=publisher)

        app = FastAPI()
        app.add_middleware(
            RequestMonitoringMiddleware,
            telemetry=telemetry,
            logger=logging.getLogger("test.monitoring"),
        )

        @app.get("/ok")
        def ok_endpoint():
            return {"ok": True}

        @app.get("/boom")
        def boom_endpoint():
            raise RuntimeError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/ok").status_code == 200
        assert client.get("/boom").status_code == 500
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)
        override_publisher(previous_publisher)

    snapshot = telemetry.snapshot()
    assert snapshot["total_requests"] == 2
    assert snapshot["error_requests"] == 1
    assert "GET /ok" in snapshot["endpoints"]
    assert snapshot["endpoints"]["GET /boom"]["error_requests"] == 1

    messages = {record["message"] for record in publisher.records}
    assert "request.completed" in messages
    assert "request.failed" in messages
