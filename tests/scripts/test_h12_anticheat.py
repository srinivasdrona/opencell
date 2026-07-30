"""Anti-laundering guard for scripts/l22_evidence/h12.py.

Statically verifies (via AST inspection, not just code review) that every
``predict_<process>`` function in ``h12.py``:
  - has a parameter signature that structurally excludes any states_after /
    SUT-derived input (only ``seed``, ``before``, ``fixture`` are allowed),
  - never references a forbidden identifier (``after``, ``states_after``,
    ``next_update``, ``run_oc_tick``, ``result_json``, ``evidence_bundle``),
  - never imports (module-level or local) any SUT/runner-adjacent module
    (``opencell.vivarium``, ``opencell.simulation``, any ``karr_*`` OC port,
    or the harness's own oracle-loading helper module).

This test must keep passing after any edit to h12.py. If a genuine formula
cannot be derived without one of these forbidden inputs, the correct fix is
to mark that process's H12 evidence as FAIL, not to weaken this test.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

H12_PATH = REPO_ROOT / "scripts" / "l22_evidence" / "h12.py"

FORBIDDEN_IMPORT_SUBSTRINGS = (
    "opencell.vivarium",
    "opencell.simulation",
    "runner_helpers",
    "_l2_2_design_a_runner_helpers",
    "karr_macromolecular_complexation",
    "karr_protein_folding",
    "karr_protein_processing_i",
    "karr_protein_processing_ii",
    "karr_trna_aminoacylation",
)

FORBIDDEN_IDENTIFIERS = {
    "after",
    "states_after",
    "next_update",
    "run_oc_tick",
    "result_json",
    "evidence_bundle",
}

ALLOWED_PREDICTOR_PARAMS = {"seed", "before", "fixture"}


def _module_ast() -> ast.Module:
    source = H12_PATH.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(H12_PATH))


def _all_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            yield mod
            for alias in node.names:
                yield f"{mod}.{alias.name}" if mod else alias.name


def _predictor_functions(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("predict_"):
            yield node


def test_h12_module_exists():
    assert H12_PATH.exists(), "scripts/l22_evidence/h12.py must exist"


def test_no_forbidden_module_imports_anywhere():
    tree = _module_ast()
    imports = list(_all_imports(tree))
    for imp in imports:
        for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
            assert forbidden not in imp, (
                f"h12.py imports forbidden module/name {imp!r} "
                f"(matches forbidden substring {forbidden!r}) — predictor "
                f"independence would be compromised"
            )


def test_predictor_registry_is_nonempty():
    tree = _module_ast()
    predictors = list(_predictor_functions(tree))
    assert len(predictors) >= 5, "expected at least 5 predict_* functions (one per target process)"


@pytest.mark.parametrize(
    "process",
    [
        "macromolecular_complexation",
        "protein_processing_i",
        "protein_processing_ii",
        "protein_folding",
        "trna_aminoacylation",
    ],
)
def test_predictor_signature_excludes_forbidden_inputs(process):
    tree = _module_ast()
    fn = next((n for n in _predictor_functions(tree) if n.name == f"predict_{process}"), None)
    assert fn is not None, f"predict_{process} not found in h12.py"

    params = [a.arg for a in fn.args.args]
    assert set(params) <= ALLOWED_PREDICTOR_PARAMS, (
        f"predict_{process} has parameter(s) {set(params) - ALLOWED_PREDICTOR_PARAMS} "
        f"outside the allowed anti-laundering input set {ALLOWED_PREDICTOR_PARAMS}"
    )


@pytest.mark.parametrize(
    "process",
    [
        "macromolecular_complexation",
        "protein_processing_i",
        "protein_processing_ii",
        "protein_folding",
        "trna_aminoacylation",
    ],
)
def test_predictor_body_has_no_forbidden_identifiers(process):
    tree = _module_ast()
    fn = next((n for n in _predictor_functions(tree) if n.name == f"predict_{process}"), None)
    assert fn is not None

    names_used = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            names_used.add(node.id)
        elif isinstance(node, ast.Attribute):
            names_used.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names_used.add(node.value)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            pytest.fail(f"predict_{process} contains a local import ({ast.dump(node)}) — forbidden")

    offending = names_used & FORBIDDEN_IDENTIFIERS
    assert not offending, (
        f"predict_{process} references forbidden identifier(s) {offending} — "
        f"predictors must only use `before` (states_before) and `fixture` "
        f"(static Karr parameters), never states_after/SUT/result artifacts"
    )


def test_compare_predictions_is_the_only_states_after_consumer():
    """states_after (loaded as `after` in load_oracle_seed / run_h12) must
    only be dereferenced inside compare_predictions — never inside a
    predict_* function. We check this by confirming every predict_* function
    body (already checked above) has zero references to `after`, and that
    `compare_predictions` is the function that receives an `after` parameter.
    """
    tree = _module_ast()
    compare_fn = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "compare_predictions"),
        None,
    )
    assert compare_fn is not None, "compare_predictions() must exist"
    params = [a.arg for a in compare_fn.args.args]
    assert "after" in params, "compare_predictions must be the function receiving states_after"


def test_predictors_module_docstring_states_the_contract():
    source = H12_PATH.read_text(encoding="utf-8")
    assert "ANTI-LAUNDERING CONTRACT" in source
    assert "states_after" in source
