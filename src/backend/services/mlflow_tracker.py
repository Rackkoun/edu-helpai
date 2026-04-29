# file src/backend/services/mlflow_tracker.py

import time
import mlflow
from src.backend.config import settings


def _setup_mlflow() -> None:
    """Configure MLflow tracking URI and experiment once"""
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)


async def track_query(user_query: str, llm_response: str, session_id: str, latency_ms: float = 0.0) -> None:
    """
        Log Q&A turn to MLflow
        Called after a response is complete
    """
    try:
        _setup_mlflow()
        with mlflow.start_run(run_name=f"query_{session_id[:8]}"):
            mlflow.log_params({
                "session_id": session_id,
                "model": settings.OLLAMA_MODEL,
                "embedding_model": settings.EMBEDDING_MODEL,
                "top_k": settings.RAG_TOP_K,
                "chunk_size": settings.CHUNK_SIZE,
            })

            mlflow.log_metrics({
                "query_length": len(user_query),
                "response_length": len(llm_response),
                "latency_ms": latency_ms,
            })

            mlflow.set_tags({
                "environment": settings.ENVIRONMENT,
                "query_preview": user_query[:100],
            })
    except Exception:
        pass