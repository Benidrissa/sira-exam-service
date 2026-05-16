"""Tests for E3-10 — VLM config + edge result storage."""
from __future__ import annotations

import uuid


def test_vlm_config_response_schema_defaults() -> None:
    from app.schemas.proctor import VLMConfigResponse
    cfg = VLMConfigResponse(model_version="v1.0.0", cdn_base="https://cdn.example.com")
    assert cfg.mandatory_sample_rate == 0.10
    assert cfg.tier2_model is None
    assert isinstance(cfg.tier1_models, list)


def test_edge_result_request_schema() -> None:
    from datetime import UTC, datetime

    from app.schemas.proctor import EdgeResultRequest
    req = EdgeResultRequest(
        snapshot_id=uuid.uuid4(),
        captured_at=datetime.now(UTC),
        edge_decision="clean",
        edge_confidence=0.92,
        edge_inference_ms=112,
        model_version="v1.0.0",
    )
    assert req.violation_type == "none"
    assert req.edge_confidence == 0.92


def test_migration_007_exists_and_has_correct_down_revision() -> None:
    import importlib.util
    import pathlib
    migration_dir = pathlib.Path(__file__).parent.parent / "migrations" / "versions"
    migration_007 = migration_dir / "007_edge_metadata_session.py"
    assert migration_007.exists(), "Migration 007 file must exist"
    spec = importlib.util.spec_from_file_location("m007", migration_007)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "007"
    assert mod.down_revision == "006"
