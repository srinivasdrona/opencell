"""Tests for Phase 1 remaining components:
- observation model, validation harness, replay/delta ledger
- panel, pipeline, I/O manifests, naked numbers lint
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from opencell.analysis.observation import AssayDefinition, ObservationModel, od600_assay, qpcr_assay
from opencell.core.validation import (
    ValidationHarness,
    mass_conservation_validator,
    positivity_validator,
    doubling_time_validator,
)
from opencell.core.replay import DeltaLedger, StepReplay
from opencell.core.io_manifests import IOManifest, ManifestRegistry
from opencell.orchestrator.panel import Claim, ClaimGraph, Confidence, EvidenceItem, ExpertPanel
from opencell.orchestrator.pipeline import OpenCellPipeline


# ── Observation Model tests ──

class TestObservationModel:
    def test_register_and_observe(self) -> None:
        model = ObservationModel()
        assay = od600_assay(extinction_coeff=1.5)
        model.register_assay(assay)
        state = {"biomass": 2.0}
        result = model.observe("OD600", state)
        assert abs(result - 3.0) < 1e-10  # 1.5 * 1.0 * 2.0

    def test_observe_unknown_assay(self) -> None:
        model = ObservationModel()
        with pytest.raises(KeyError, match="Unknown assay"):
            model.observe("nonexistent", {})

    def test_qpcr_assay(self) -> None:
        model = ObservationModel()
        model.register_assay(qpcr_assay("geneA", amplification_efficiency=0.9))
        state = {"mRNA_geneA": 100.0}
        result = model.observe("qPCR_geneA", state)
        assert abs(result - 90.0) < 1e-10

    def test_detection_limit(self) -> None:
        model = ObservationModel()
        model.register_assay(qpcr_assay("geneB"))
        state = {"mRNA_geneB": 0.5}  # below detection limit of 1.0
        result = model.observe("qPCR_geneB", state)
        assert result == 0.0

    def test_observe_all(self) -> None:
        model = ObservationModel()
        model.register_assay(od600_assay())
        model.register_assay(qpcr_assay("geneA"))
        state = {"biomass": 1.0, "mRNA_geneA": 50.0}
        results = model.observe_all(state)
        assert "OD600" in results
        assert "qPCR_geneA" in results

    def test_noise_gaussian(self) -> None:
        model = ObservationModel()
        model.register_assay(od600_assay())
        state = {"biomass": 1.0}
        rng = np.random.default_rng(42)
        values = [model.observe("OD600", state, add_noise=True, rng=rng) for _ in range(100)]
        assert not all(v == values[0] for v in values)  # noise adds variation


# ── Validation Harness tests ──

class TestValidationHarness:
    def test_mass_conservation_pass(self) -> None:
        validator = mass_conservation_validator(tolerance=1e-6)
        ctx = {"initial_total_mass": 100.0, "final_total_mass": 100.0}
        result = validator(ctx)
        assert result.passed

    def test_mass_conservation_fail(self) -> None:
        validator = mass_conservation_validator(tolerance=1e-6)
        ctx = {"initial_total_mass": 100.0, "final_total_mass": 110.0}
        result = validator(ctx)
        assert not result.passed

    def test_positivity_pass(self) -> None:
        validator = positivity_validator()
        ctx = {"final_counts": {"A": 10.0, "B": 0.0}}
        result = validator(ctx)
        assert result.passed

    def test_positivity_fail(self) -> None:
        validator = positivity_validator()
        ctx = {"final_counts": {"A": 10.0, "B": -0.001}}
        result = validator(ctx)
        assert not result.passed

    def test_harness_aggregation(self) -> None:
        harness = ValidationHarness()
        harness.add_validator("mass", mass_conservation_validator())
        harness.add_validator("positivity", positivity_validator())
        ctx = {
            "initial_total_mass": 100.0,
            "final_total_mass": 100.0,
            "final_counts": {"A": 50.0},
        }
        report = harness.validate(ctx)
        assert report.passed
        assert report.n_passed == 2

    def test_harness_summary(self) -> None:
        harness = ValidationHarness()
        harness.add_validator("mass", mass_conservation_validator())
        ctx = {"initial_total_mass": 100.0, "final_total_mass": 100.0}
        report = harness.validate(ctx)
        summary = report.summary()
        assert "2/2" in summary or "1/1" in summary


# ── Delta Ledger / Replay tests ──

class TestDeltaLedger:
    def test_record_and_report(self) -> None:
        ledger = DeltaLedger()
        ledger.begin_step(0, 0.0, 0.01, {"A": 100.0, "B": 0.0})
        ledger.record_delta("producer", "A", 10.0, "constant production")
        ledger.record_delta("consumer", "A", -5.0, "first-order decay")
        ledger.record_delta("consumer", "B", 5.0, "product formation")
        step = ledger.end_step({"A": 105.0, "B": 5.0})

        assert len(step.contributions_for("A")) == 2
        assert len(step.contributions_for("B")) == 1
        report = step.report("A")
        assert "producer" in report
        assert "consumer" in report

    def test_find_first_bad_step(self) -> None:
        ledger = DeltaLedger()
        for i in range(3):
            val = 10.0 - i * 5
            ledger.begin_step(i, i * 0.01, 0.01, {"X": val})
            ledger.record_delta("mod", "X", -5.0)
            ledger.end_step({"X": val - 5.0})

        bad = ledger.find_first_bad_step("X", threshold=0.0)
        assert bad is not None
        assert bad.step_index == 2  # X goes from 0 to -5

    def test_no_step_raises(self) -> None:
        ledger = DeltaLedger()
        with pytest.raises(RuntimeError, match="No step"):
            ledger.record_delta("mod", "X", 1.0)


# ── I/O Manifests tests ──

class TestManifestRegistry:
    def test_register_and_check(self) -> None:
        reg = ManifestRegistry()
        manifest = IOManifest(
            module_id="metabolism",
            reads={"glucose": "mM"},
            writes={"atp": "mM", "co2": "mM"},
        )
        reg.register(manifest)
        assert "metabolism" in reg.module_ids

    def test_undeclared_writes(self) -> None:
        reg = ManifestRegistry()
        reg.register(IOManifest(module_id="mod", writes={"A": "mM"}))
        errors = reg.check_undeclared_writes("mod", {"A", "B"})
        assert len(errors) == 1
        assert "B" in errors[0]

    def test_unit_consistency(self) -> None:
        reg = ManifestRegistry()
        reg.register(IOManifest(module_id="mod", reads={"A": "mM"}))
        errors = reg.check_unit_consistency("mod", {"A": "µM"})
        assert len(errors) == 1


# ── Panel tests ──

class TestPanel:
    def test_deliberate_returns_claim_graph(self) -> None:
        panel = ExpertPanel()
        graph = panel.deliberate("What kinetic law for G6PI?")
        assert isinstance(graph, ClaimGraph)
        assert graph.needs_human_review
        assert len(graph.panel_models) == 3

    def test_claim_graph_unverified_dois(self) -> None:
        graph = ClaimGraph(question="test")
        graph.claims.append(Claim(
            claim_text="Test claim",
            evidence_for=[EvidenceItem(doi="10.1016/test", excerpt="...")],
            confidence=Confidence.HIGH,
        ))
        dois = graph.unverified_dois()
        assert "10.1016/test" in dois

    def test_doi_validation(self) -> None:
        panel = ExpertPanel()
        assert panel.verify_doi("10.1016/j.cell.2023")
        assert not panel.verify_doi("")
        assert not panel.verify_doi("not-a-doi")


# ── Pipeline tests ──

class TestPipeline:
    def test_build_submodel(self, tmp_path: Path) -> None:
        pipeline = OpenCellPipeline(decisions_dir=tmp_path / "decisions")
        results = pipeline.build_submodel("metabolism")
        assert len(results) == 6  # panel + routing + 4 placeholder steps
        assert all(r.success for r in results)

    def test_build_all(self, tmp_path: Path) -> None:
        pipeline = OpenCellPipeline(decisions_dir=tmp_path / "decisions")
        results = pipeline.build_all("toy_cell")
        assert "metabolism" in results
        assert "transcription" in results
        assert "translation" in results
