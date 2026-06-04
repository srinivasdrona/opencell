"""Vivarium Process port of Karr's ProteinActivation boolean rule logic.

Rules are loaded from `ProteinActivation_flat.mat` and compiled at init time
into pure callables of the form `rule(signal_counts) -> bool`.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinActivation_flat.mat"
_REGULATED_PROTEINS = (
    "MG_085_HEXAMER",
    "MG_101_MONOMER",
    "MG_127_MONOMER",
    "MG_205_DIMER",
    "MG_236_MONOMER",
    "MG_409_DIMER",
)


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return ""
        out = out.flat[0]
    return out


def _parse_wid_array(cell_array: np.ndarray) -> list[str]:
    values = np.asarray(cell_array, dtype=object)
    return [str(_coerce_scalar(raw)) for raw in values.ravel()]


def _parse_stimulus_defaults(stimuli: object, n_stimuli: int) -> list[float]:
    values = np.asarray(stimuli, dtype=np.float64)
    if values.ndim == 0:
        return [float(values)] * n_stimuli
    if values.ndim == 1:
        vector = values.reshape(-1)
    else:
        # Karr stores process stimuli by compartment; evaluateActivationRules uses a
        # single compartment slice per tick in this replay harness.
        vector = values[:, 0].reshape(-1)

    out = [0.0] * n_stimuli
    n = min(n_stimuli, int(vector.shape[0]))
    for idx in range(n):
        out[idx] = float(vector[idx])
    return out


def _sanitize_rule_text(rule: str) -> str:
    text = rule.strip()
    text = text.replace("&&", "&").replace("||", "|")
    text = text.replace("~", " not ")
    text = text.replace("&", " and ").replace("|", " or ")
    return re.sub(r"\s+", " ", text).strip()


def _assert_rule_ast_is_safe(tree: ast.AST) -> None:
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.UnaryOp,
        ast.BinOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"Unsupported activation rule syntax: {type(node).__name__}")


def _compile_rule(raw_rule: object) -> tuple[Callable[[dict[str, float]], bool], str, set[str]]:
    rule = _coerce_scalar(raw_rule)

    if callable(rule):
        return (lambda signals, fn=rule: bool(fn(signals))), "<callable-rule>", set()

    if not isinstance(rule, str):
        raise TypeError(f"Unsupported activation rule type: {type(rule).__name__}")

    normalized = _sanitize_rule_text(rule)
    tree = ast.parse(normalized, mode="eval")
    _assert_rule_ast_is_safe(tree)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    code = compile(tree, "<protein-activation-rule>", "eval")

    def _rule_eval(signals: dict[str, float]) -> bool:
        namespace = {name: float(signals.get(name, 0.0)) for name in names}
        return bool(eval(code, {"__builtins__": {}}, namespace))  # noqa: S307 - guarded AST

    return _rule_eval, rule, names


class KarrProteinActivationProcess(Process):
    """Karr Process_ProteinActivation (deterministic boolean activation)."""

    name = "karr_protein_activation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        fixture_path = _resolve_fixture_path(self.parameters["fixture_path"])
        fixture = loadmat(str(fixture_path), squeeze_me=True, struct_as_record=False)[
            "data"
        ].fixture

        self.substrate_wids = _parse_wid_array(fixture.substrateWholeCellModelIDs)
        self.stimuli_wids = _parse_wid_array(fixture.stimuliWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fixture.enzymeWholeCellModelIDs)
        self.default_stimuli = dict(
            zip(
                self.stimuli_wids,
                _parse_stimulus_defaults(fixture.stimuli, len(self.stimuli_wids)),
                strict=False,
            )
        )
        self._substrate_wid_set = set(self.substrate_wids)
        self._stimuli_wid_set = set(self.stimuli_wids)

        raw_rules = np.asarray(fixture.activationRules, dtype=object).ravel().tolist()
        if len(raw_rules) != len(self.substrate_wids):
            raise ValueError(
                "ProteinActivation fixture mismatch: "
                f"{len(raw_rules)} rules for {len(self.substrate_wids)} substrates"
            )

        self.rule_strings: dict[str, str] = {}
        self.rules: dict[str, Callable[[dict[str, float]], bool]] = {}
        self.regulated_protein_wids = [
            wid for wid in _REGULATED_PROTEINS if wid in self.substrate_wids
        ]
        if len(self.regulated_protein_wids) != len(_REGULATED_PROTEINS):
            missing = sorted(set(_REGULATED_PROTEINS) - set(self.regulated_protein_wids))
            raise ValueError(f"Missing regulated proteins in fixture: {missing}")

        rule_by_wid = {wid: raw_rules[idx] for idx, wid in enumerate(self.substrate_wids)}
        referenced: set[str] = set()
        for wid in self.regulated_protein_wids:
            compiled, source, names = _compile_rule(rule_by_wid[wid])
            self.rules[wid] = compiled
            self.rule_strings[wid] = source
            referenced.update(names)

        unknown_names = referenced - self._substrate_wid_set - self._stimuli_wid_set
        if unknown_names:
            raise ValueError(f"Activation rule references unknown signals: {sorted(unknown_names)}")
        self._referenced_names = sorted(referenced)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "inactivatedSubstrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.enzyme_wids
            },
            "stimuli": {
                wid: {
                    "_default": float(self.default_stimuli.get(wid, 0.0)),
                    "_updater": "set",
                    "_emit": False,
                }
                for wid in self.stimuli_wids
            },
            "protein": {
                "activity": {
                    wid: {"_default": 0, "_updater": "set", "_emit": True}
                    for wid in self.regulated_protein_wids
                }
            },
        }

    def _collect_rule_signals(self, states: dict[str, Any]) -> dict[str, float]:
        substrate_state = states.get("substrates", {})
        stimuli_state = states.get("stimuli", {})
        out: dict[str, float] = {}
        for name in self._referenced_names:
            if name in self._substrate_wid_set:
                out[name] = float(substrate_state.get(name, 0.0))
            else:
                out[name] = float(stimuli_state.get(name, 0.0))
        return out

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        signals = self._collect_rule_signals(states)
        substrates_state = states.get("substrates", {})
        inactivated_state = states.get("inactivatedSubstrates", {})

        activity_update: dict[str, int] = {}
        substrate_delta: dict[str, float] = {}
        inactivated_delta: dict[str, float] = {}

        for wid in self.regulated_protein_wids:
            is_active = int(self.rules[wid](signals))
            activity_update[wid] = is_active

            active_now = float(substrates_state.get(wid, 0.0))
            inactive_now = float(inactivated_state.get(wid, 0.0))

            if is_active:
                if inactive_now != 0.0:
                    substrate_delta[wid] = substrate_delta.get(wid, 0.0) + inactive_now
                    inactivated_delta[wid] = inactivated_delta.get(wid, 0.0) - inactive_now
            else:
                if active_now != 0.0:
                    substrate_delta[wid] = substrate_delta.get(wid, 0.0) - active_now
                    inactivated_delta[wid] = inactivated_delta.get(wid, 0.0) + active_now

        update: dict[str, Any] = {"protein": {"activity": activity_update}}
        if substrate_delta:
            update["substrates"] = substrate_delta
        if inactivated_delta:
            update["inactivatedSubstrates"] = inactivated_delta
        return update


__all__ = ["KarrProteinActivationProcess"]
