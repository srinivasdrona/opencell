"""Tests for data layer: loader, SBML I/O, contracts, router, cost tracker."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from opencell.data.loader import (
    load_json,
    load_parameters,
    load_yaml,
    validate_parameter_entry,
)
from opencell.data.sbml_io import export_sbml, import_sbml
from opencell.core.ir import (
    Compartment,
    IRSpeciesRegistry,
    MoleculeType,
    ReactionInfo,
    ReferenceFrame,
    SpeciesInfo,
)
from opencell.orchestrator.contracts import validate_data, validate_parameter_file
from opencell.orchestrator.router import ModelRouter, TaskType, Tier
from opencell.orchestrator.cost_tracker import APICallRecord, CostTracker


# ── Loader tests ──

class TestLoader:
    def test_load_yaml(self, tmp_path: Path) -> None:
        data = {"key": "value", "number": 42}
        f = tmp_path / "test.yaml"
        f.write_text(yaml.dump(data))
        result = load_yaml(f)
        assert result == data

    def test_load_json(self, tmp_path: Path) -> None:
        data = {"key": "value", "number": 42}
        f = tmp_path / "test.json"
        f.write_text(json.dumps(data))
        result = load_json(f)
        assert result == data

    def test_load_parameters_yaml(self, tmp_path: Path) -> None:
        data = {"parameters": [{"value": 1.0}]}
        f = tmp_path / "params.yml"
        f.write_text(yaml.dump(data))
        result = load_parameters(f)
        assert result["parameters"][0]["value"] == 1.0

    def test_load_parameters_json(self, tmp_path: Path) -> None:
        data = {"parameters": [{"value": 2.0}]}
        f = tmp_path / "params.json"
        f.write_text(json.dumps(data))
        result = load_parameters(f)
        assert result["parameters"][0]["value"] == 2.0

    def test_load_parameters_unsupported(self, tmp_path: Path) -> None:
        f = tmp_path / "params.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            load_parameters(f)

    def test_validate_entry_valid(self) -> None:
        entry = {"value": 1.0, "unit": "mM", "source": "BRENDA"}
        errors = validate_parameter_entry(entry, "km_g6pi")
        assert errors == []

    def test_validate_entry_missing_fields(self) -> None:
        entry = {"value": 1.0}
        errors = validate_parameter_entry(entry, "km_g6pi")
        assert len(errors) == 2  # missing unit, source

    def test_validate_entry_empty_source(self) -> None:
        entry = {"value": 1.0, "unit": "mM", "source": ""}
        errors = validate_parameter_entry(entry, "km_g6pi")
        assert any("empty source" in e for e in errors)


# ── SBML I/O tests ──

class TestSBMLIO:
    def _build_registry(self) -> tuple[IRSpeciesRegistry, list[ReactionInfo], dict[str, float]]:
        reg = IRSpeciesRegistry()
        reg.register(SpeciesInfo(
            id="glucose", name="Glucose",
            compartment=Compartment.CYTOPLASM,
            molecule_type=MoleculeType.METABOLITE,
            reference_frame=ReferenceFrame.PER_CELL,
        ))
        reg.register(SpeciesInfo(
            id="atp", name="ATP",
            compartment=Compartment.CYTOPLASM,
            molecule_type=MoleculeType.METABOLITE,
            reference_frame=ReferenceFrame.PER_CELL,
        ))
        reactions = [
            ReactionInfo(
                id="glycolysis_step1",
                name="Hexokinase",
                stoichiometry={"glucose": -1, "atp": -1},
                reversible=False,
            ),
        ]
        initial_counts = {"glucose": 1000.0, "atp": 5000.0}
        return reg, reactions, initial_counts

    def test_export_creates_file(self, tmp_path: Path) -> None:
        reg, reactions, counts = self._build_registry()
        out = tmp_path / "model.sbml"
        result = export_sbml(out, reg, reactions, counts)
        assert result.exists()
        content = result.read_text()
        assert "glucose" in content
        assert "atp" in content

    def test_import_roundtrip(self, tmp_path: Path) -> None:
        reg, reactions, counts = self._build_registry()
        out = tmp_path / "model.sbml"
        export_sbml(out, reg, reactions, counts)

        reg2, reactions2, counts2 = import_sbml(out)
        assert "glucose" in reg2.ids
        assert "atp" in reg2.ids
        assert len(reactions2) == 1
        assert reactions2[0].id == "glycolysis_step1"
        assert abs(counts2["glucose"] - 1000.0) < 1e-10

    def test_stoichiometry_preserved(self, tmp_path: Path) -> None:
        reg, reactions, counts = self._build_registry()
        out = tmp_path / "model.sbml"
        export_sbml(out, reg, reactions, counts)
        _, reactions2, _ = import_sbml(out)
        stoich = reactions2[0].stoichiometry
        assert stoich["glucose"] == -1.0
        assert stoich["atp"] == -1.0


# ── Contracts tests ──

class TestContracts:
    def test_valid_parameter(self) -> None:
        data = {
            "parameter_id": "km_g6pi",
            "value": 0.5,
            "unit": "mM",
            "source": {"doi": "10.1016/test"},
            "confidence": "measured",
        }
        errors = validate_data(data, "parameter")
        assert errors == []

    def test_invalid_parameter_missing_required(self) -> None:
        data = {"parameter_id": "km_g6pi", "value": 0.5}
        errors = validate_data(data, "parameter")
        assert len(errors) > 0  # missing unit, source, confidence

    def test_invalid_confidence_value(self) -> None:
        data = {
            "parameter_id": "km",
            "value": 1.0,
            "unit": "mM",
            "source": {"doi": "10.1016/test"},
            "confidence": "guessed",  # not in enum
        }
        errors = validate_data(data, "parameter")
        assert len(errors) > 0

    def test_validate_parameter_file_yaml(self, tmp_path: Path) -> None:
        data = {
            "parameter_id": "vmax_hk",
            "value": 120.0,
            "unit": "µmol/min/mg",
            "source": {"doi": "10.1074/test"},
            "confidence": "estimated",
        }
        f = tmp_path / "params.yaml"
        f.write_text(yaml.dump(data))
        errors = validate_parameter_file(f)
        assert errors == []


# ── Router tests ──

class TestRouter:
    def test_route_critical(self) -> None:
        router = ModelRouter()
        model, temp = router.route(Tier.CRITICAL, TaskType.BIOLOGY_DECISION)
        assert model.provider in ("anthropic", "openai", "xai")
        assert temp == 0.0

    def test_route_routine(self) -> None:
        router = ModelRouter()
        model, temp = router.route(Tier.ROUTINE, TaskType.DATA_FORMATTING)
        assert model.provider == "anthropic"
        assert temp == 0.0

    def test_route_literature_search_has_temperature(self) -> None:
        router = ModelRouter()
        _, temp = router.route(Tier.STANDARD, TaskType.LITERATURE_SEARCH)
        assert temp == 0.3

    def test_route_web_search(self) -> None:
        router = ModelRouter()
        model, _ = router.route(Tier.STANDARD, needs_web=True)
        assert model.supports_web

    def test_route_no_models_raises(self) -> None:
        router = ModelRouter(models={})
        with pytest.raises(ValueError, match="No models"):
            router.route(Tier.CRITICAL, TaskType.CODE_GENERATION)


# ── Cost Tracker tests ──

class TestCostTracker:
    def test_log_and_summary(self, tmp_path: Path) -> None:
        db = tmp_path / "costs.db"
        tracker = CostTracker(db)

        record = APICallRecord(
            timestamp="2026-04-22T10:00:00Z",
            model_id="claude-opus-4",
            tier="CRITICAL",
            task_type="BIOLOGY_DECISION",
            phase="Phase 2",
            input_tokens=5000,
            output_tokens=2000,
            estimated_cost_usd=0.225,
        )
        tracker.log_call(record)

        summary = tracker.summary()
        assert summary["total_calls"] == 1
        assert summary["total_input_tokens"] == 5000
        assert summary["total_cost_usd"] == 0.225

    def test_estimate_cost(self) -> None:
        cost = CostTracker.estimate_cost("claude-haiku", 100_000, 10_000)
        expected = (100_000 * 0.25 + 10_000 * 1.25) / 1_000_000
        assert abs(cost - expected) < 1e-6

    def test_by_tier(self, tmp_path: Path) -> None:
        db = tmp_path / "costs.db"
        tracker = CostTracker(db)
        for tier in ["CRITICAL", "ROUTINE"]:
            tracker.log_call(APICallRecord(
                timestamp="2026-04-22T10:00:00Z",
                model_id="claude-haiku", tier=tier,
                task_type="TEST", phase="Phase 1",
                input_tokens=100, output_tokens=50,
                estimated_cost_usd=0.001,
            ))
        results = tracker.by_tier()
        assert len(results) == 2
