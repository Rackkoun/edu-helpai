# file tests/test_mlflow_tracker.py

import pytest
from unittest.mock import patch, MagicMock
from src.backend.services.mlflow_tracker import track_query


@pytest.mark.asyncio
async def test_track_query_logs_run() -> None:
    """track_query should create a MLflow run without raising"""
    with patch("src.backend.services.mlflow_tracker.mlflow") as mock_mlflow:
        mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=None)
        mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

        await track_query(
            user_query="What is an algorithm?",
            llm_response="An algorithm is ...",
            session_id="test-session-123",
            latency_ms=250.0,
        )

    mock_mlflow.set_tracking_uri.assert_called_once()
    mock_mlflow.set_experiment.assert_called_once()
    mock_mlflow.start_run.assert_called_once()


@pytest.mark.asyncio
async def test_track_query_swallows_exception() -> None:
    """MLflow errors must never propage to the request path"""

    with patch(
        "src.backend.services.mlflow_tracker.mlflow.set_tracking_uri",
        side_effect=Exception("MLflow down"),
    ):
        # should not raise
        await track_query("query", "response", "session-id")
