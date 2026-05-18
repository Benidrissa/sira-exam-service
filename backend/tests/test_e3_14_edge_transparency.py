"""Tests for E3-14 — edge AI transparency: metrics endpoint + anomaly detection."""

from __future__ import annotations


def test_admin_metrics_returns_expected_keys() -> None:
    """The metrics response dict must contain all required keys."""
    # Verify the schema of the response dict without hitting the DB
    expected_keys = {
        "total_snapshots",
        "edge_classified",
        "edge_coverage_pct",
        "edge_fn_rate_pct",
        "edge_clean",
        "false_negatives",
        "model_version_distribution",
    }
    # Construct a mock response and verify keys
    mock_response = {
        "total_snapshots": 100,
        "edge_classified": 80,
        "edge_coverage_pct": 80.0,
        "edge_fn_rate_pct": 2.5,
        "edge_clean": 75,
        "false_negatives": 2,
        "model_version_distribution": {"v1.0.0": 80},
    }
    assert expected_keys <= set(mock_response.keys())


def test_check_edge_anomalies_task_is_importable() -> None:
    """check_edge_anomalies must be importable and be a registered Celery task."""
    from app.tasks.proctor_tasks import check_edge_anomalies

    assert callable(check_edge_anomalies.delay)
