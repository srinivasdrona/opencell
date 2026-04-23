"""Generic SBML L2/L3 → ODE system translator using libsbml + sympy.

Compiles each ``<kineticLaw>`` and ``<assignmentRule>`` MathML expression to
a Python callable via :func:`sympy.lambdify` (NumPy backend).  This produces
a deterministic, audit-friendly RHS function suitable for handoff to the
existing :mod:`opencell.solvers.ode_scipy` integrator.

Supported SBML features (sufficient for BIOMD0000000051 / Chassagnole 2002
and BIOMD0000000035 / Vilar 2002):

* Dynamic species in either concentration mode (default) or amount mode
  (``hasOnlySubstanceUnits=true``); per-species handling
* Boundary / constant species (treated as fixed environment)
* Global parameters (constant or driven by assignment rules)
* Local parameters per ``<kineticLaw>``
* Assignment rules (cofactors as time-dependent forcing functions)
* Multi-compartment models with constant compartment sizes

Explicitly refused (loud failure, never silent best-effort):

* ``<event>`` elements
* ``<functionDefinition>`` (we do not unfold custom MathML lambdas yet)
* ``<rateRule>`` and ``<algebraicRule>``
* ``<initialAssignment>`` (initial values must be literal in the SBML)

Provenance: every loaded model records the SBML file path and the SHA-256 of
its bytes so any simulation output can be traced back to the exact source.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

try:
    import libsbml
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "python-libsbml is required for opencell.models.sbml_model. "
        "Install with: pip install python-libsbml"
    ) from exc

import sympy
from sympy.parsing.sympy_parser import parse_expr


# Identifier tokens we must NOT shadow with bare Symbols — these are SBML
# infix functions/constants that sympy already understands correctly.
_SBML_RESERVED = frozenset(
    {
        "pow", "exp", "log", "log10", "ln", "sqrt", "abs",
        "sin", "cos", "tan", "asin", "acos", "atan",
        "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
        "sec", "csc", "cot",
        "floor", "ceiling", "factorial",
        "min", "max", "piecewise",
        "and", "or", "not", "xor", "true", "false",
        "gt", "lt", "geq", "leq", "eq", "neq",
        "pi", "exponentiale", "infinity", "notanumber",
        "True", "False",
    }
)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---------------------------------------------------------------------------
# Compiled formula container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledFormula:
    """A MathML/infix formula compiled to a NumPy-backed callable.

    Attributes:
        source: original infix string from ``libsbml.formulaToString``
        symbols: ordered list of free-symbol names (matches ``fn`` arg order)
        fn: callable(*values) -> float
    """

    source: str
    symbols: tuple[str, ...]
    fn: Callable[..., float]


def _compile_formula(formula: str, *, context: str = "") -> CompiledFormula:
    """Parse an SBML infix formula and lambdify with NumPy.

    Identifiers are pre-bound to ``sympy.Symbol`` to prevent collisions with
    sympy's singleton registry (e.g. ``S`` → ``sympy.S``, ``I`` → ``ImaginaryUnit``,
    ``E`` → Euler's number, ``Q`` → rationals).  This is essential: SBML files
    in the wild use ``S`` for substrate, ``E`` for enzyme, ``I`` for inhibitor.

    Args:
        formula: infix string from :func:`libsbml.formulaToString`
        context: human-readable context (e.g. reaction id) used in errors

    Raises:
        ValueError: if sympy cannot parse the formula
    """
    idents = set(_IDENT_RE.findall(formula)) - _SBML_RESERVED
    local_dict: dict[str, Any] = {name: sympy.Symbol(name) for name in idents}
    try:
        expr = parse_expr(formula, local_dict=local_dict, evaluate=False)
    except (SyntaxError, TypeError, sympy.SympifyError) as exc:
        raise ValueError(
            f"Failed to parse SBML formula in {context!r}: {formula!r} ({exc})"
        ) from exc
    free_names = {str(s) for s in expr.free_symbols}
    symbols = tuple(sorted(idents & free_names))
    fn = sympy.lambdify(symbols, expr, modules="numpy")
    return CompiledFormula(source=formula, symbols=symbols, fn=fn)


# ---------------------------------------------------------------------------
# Reaction container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledReaction:
    """A single reaction with its compiled kinetic law and local parameters.

    Attributes:
        sbml_id: reaction id from the SBML file
        kinetic_law: compiled ``<kineticLaw>`` formula
        local_params: name -> value for parameters scoped to this reaction
    """

    sbml_id: str
    kinetic_law: CompiledFormula
    local_params: dict[str, float]


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------


@dataclass
class SbmlOdeModel:
    """SBML model loaded as an explicit ODE system.

    The ``y`` state vector contains exactly the *dynamic* species, in the
    order given by :attr:`species_ids`.  Boundary species, constant species,
    and species/parameters set by assignment rules are NOT integrated; their
    values are recomputed from ``t`` and ``y`` on every RHS evaluation.

    Time RHS (per-species, depending on its substance/concentration mode):

        amount-mode (hasOnlySubstanceUnits=true):
            dN_i/dt = sum_j stoich[i, j] * flux_j(t, y)
        concentration-mode (default):
            dC_i/dt = (1 / V_i) * sum_j stoich[i, j] * flux_j(t, y)

    where ``flux_j`` is the value returned by reaction ``j``'s kinetic law
    (in substance/time per SBML L2/L3 convention) and ``V_i`` is the volume
    of the compartment hosting species ``i``.  In ``y``, amount-mode species
    store amount (molecule count or mole quantity) and concentration-mode
    species store concentration.
    """

    sbml_path: Path
    sbml_sha256: str
    sbml_level: int
    sbml_version: int

    species_ids: list[str]
    species_compartment: dict[str, str]
    species_substance_units: dict[str, bool]  # sid → hasOnlySubstanceUnits
    initial_y: np.ndarray
    compartment_volumes: dict[str, float]

    boundary_species: dict[str, float]  # held constant throughout
    global_params: dict[str, float]
    rule_vars: list[str]
    rules: list[tuple[str, CompiledFormula]]  # (var, compiled), in document order

    reactions: list[CompiledReaction]
    stoich: np.ndarray  # shape (n_species, n_reactions)

    # ---- Construction ----

    @classmethod
    def from_file(cls, sbml_path: str | Path) -> SbmlOdeModel:
        """Load an SBML file and compile every kinetic law and assignment rule.

        Raises:
            FileNotFoundError: if ``sbml_path`` does not exist
            ValueError: on fatal SBML parse errors or unsupported features
            NotImplementedError: on events, function definitions, rate/algebraic rules
        """
        sbml_path = Path(sbml_path)
        if not sbml_path.exists():
            raise FileNotFoundError(f"SBML file not found: {sbml_path}")

        raw = sbml_path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()

        reader = libsbml.SBMLReader()
        doc = reader.readSBMLFromString(raw.decode("utf-8"))

        # Only fail on FATAL or ERROR severity, not warnings
        fatal = []
        for i in range(doc.getNumErrors()):
            err = doc.getError(i)
            if err.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
                fatal.append(err.getMessage())
        if fatal:
            raise ValueError(f"Fatal SBML parse errors in {sbml_path}: {fatal}")

        model = doc.getModel()
        if model is None:
            raise ValueError(f"No <model> element in {sbml_path}")

        # ---- Refuse unsupported features (loud failure) ----
        if model.getNumEvents() > 0:
            raise NotImplementedError(
                f"{sbml_path.name}: <event> elements not yet supported"
            )
        if model.getNumFunctionDefinitions() > 0:
            raise NotImplementedError(
                f"{sbml_path.name}: <functionDefinition> not yet supported"
            )
        if model.getNumInitialAssignments() > 0:
            raise NotImplementedError(
                f"{sbml_path.name}: <initialAssignment> not yet supported"
            )
        for i in range(model.getNumRules()):
            rule = model.getRule(i)
            if not rule.isAssignment():
                raise NotImplementedError(
                    f"{sbml_path.name}: rule type {rule.getElementName()!r} "
                    f"on {rule.getVariable()!r} not supported"
                )

        # ---- Compartments ----
        comp_volumes: dict[str, float] = {}
        for i in range(model.getNumCompartments()):
            c = model.getCompartment(i)
            size = c.getSize() if c.isSetSize() else 1.0
            comp_volumes[c.getId()] = float(size)

        # ---- Identify rule-driven variables ----
        rule_var_set: set[str] = set()
        for i in range(model.getNumRules()):
            rule_var_set.add(model.getRule(i).getVariable())

        # ---- Species ----
        dynamic_species: list[str] = []
        species_comp: dict[str, str] = {}
        species_subs: dict[str, bool] = {}
        initial_vals: list[float] = []
        boundary: dict[str, float] = {}

        for i in range(model.getNumSpecies()):
            s = model.getSpecies(i)
            sid = s.getId()
            sub_only = bool(s.getHasOnlySubstanceUnits())
            comp_id = s.getCompartment()
            vol = comp_volumes.get(comp_id, 1.0)

            # Resolve initial value into the storage convention for y:
            #   amount-mode species: y stores AMOUNT
            #   concentration-mode species: y stores CONCENTRATION
            if s.isSetInitialConcentration():
                conc = float(s.getInitialConcentration())
                init = conc * vol if sub_only else conc
            elif s.isSetInitialAmount():
                amt = float(s.getInitialAmount())
                init = amt if sub_only else (amt / vol)
            else:
                init = 0.0

            if s.getBoundaryCondition() or s.getConstant():
                boundary[sid] = float(init)
                continue
            if sid in rule_var_set:
                # Driven by assignment rule, not by ODE
                continue

            dynamic_species.append(sid)
            species_comp[sid] = comp_id
            species_subs[sid] = sub_only
            initial_vals.append(float(init))

        # ---- Global parameters ----
        global_params: dict[str, float] = {}
        for i in range(model.getNumParameters()):
            p = model.getParameter(i)
            pid = p.getId()
            if pid in rule_var_set:
                # Driven by assignment rule; skip — value will be recomputed each step
                continue
            global_params[pid] = float(p.getValue())

        # ---- Assignment rules (preserve document order) ----
        rules: list[tuple[str, CompiledFormula]] = []
        rule_vars: list[str] = []
        for i in range(model.getNumRules()):
            rule = model.getRule(i)
            var = rule.getVariable()
            formula = libsbml.formulaToString(rule.getMath())
            rules.append((var, _compile_formula(formula, context=f"rule:{var}")))
            rule_vars.append(var)

        # ---- Reactions ----
        sp_idx = {sid: k for k, sid in enumerate(dynamic_species)}
        n_sp = len(dynamic_species)
        n_rxn = model.getNumReactions()
        stoich = np.zeros((n_sp, n_rxn), dtype=np.float64)
        compiled_rxns: list[CompiledReaction] = []

        for j in range(n_rxn):
            rxn = model.getReaction(j)
            rid = rxn.getId()
            kl = rxn.getKineticLaw()
            if kl is None:
                raise ValueError(f"Reaction {rid!r} has no <kineticLaw>")
            formula = libsbml.formulaToString(kl.getMath())
            local = {
                kl.getParameter(k).getId(): float(kl.getParameter(k).getValue())
                for k in range(kl.getNumParameters())
            }
            compiled_rxns.append(
                CompiledReaction(
                    sbml_id=rid,
                    kinetic_law=_compile_formula(formula, context=f"reaction:{rid}"),
                    local_params=local,
                )
            )
            for k in range(rxn.getNumReactants()):
                sref = rxn.getReactant(k)
                if sref.getSpecies() in sp_idx:
                    stoich[sp_idx[sref.getSpecies()], j] -= float(sref.getStoichiometry())
            for k in range(rxn.getNumProducts()):
                sref = rxn.getProduct(k)
                if sref.getSpecies() in sp_idx:
                    stoich[sp_idx[sref.getSpecies()], j] += float(sref.getStoichiometry())

        return cls(
            sbml_path=sbml_path,
            sbml_sha256=sha,
            sbml_level=doc.getLevel(),
            sbml_version=doc.getVersion(),
            species_ids=dynamic_species,
            species_compartment=species_comp,
            species_substance_units=species_subs,
            initial_y=np.array(initial_vals, dtype=np.float64),
            compartment_volumes=comp_volumes,
            boundary_species=boundary,
            global_params=global_params,
            rule_vars=rule_vars,
            rules=rules,
            reactions=compiled_rxns,
            stoich=stoich,
        )

    # ---- Introspection ----

    @property
    def n_species(self) -> int:
        return len(self.species_ids)

    @property
    def n_reactions(self) -> int:
        return len(self.reactions)

    def species_index(self) -> dict[str, int]:
        """Map species id → row in y / stoichiometry matrix."""
        return {sid: k for k, sid in enumerate(self.species_ids)}

    # ---- RHS ----

    def _build_env(self, t: float, y: np.ndarray) -> dict[str, float]:
        """Build the variable lookup dict for one RHS evaluation."""
        env: dict[str, float] = {}
        env.update(self.boundary_species)
        env.update(self.global_params)
        env.update(self.compartment_volumes)
        env["t"] = float(t)
        env["time"] = float(t)
        for k, sid in enumerate(self.species_ids):
            env[sid] = float(y[k])
        # Apply assignment rules in document order — each may depend on prior ones
        for var, cf in self.rules:
            env[var] = float(cf.fn(*(env[s] for s in cf.symbols)))
        return env

    def fluxes(self, t: float, y: np.ndarray) -> np.ndarray:
        """Evaluate every reaction's kinetic law at (t, y)."""
        env = self._build_env(t, y)
        out = np.empty(self.n_reactions, dtype=np.float64)
        for j, rxn in enumerate(self.reactions):
            cf = rxn.kinetic_law
            local = rxn.local_params
            args = []
            for sym in cf.symbols:
                if sym in local:
                    args.append(local[sym])
                elif sym in env:
                    args.append(env[sym])
                else:
                    raise KeyError(
                        f"Symbol {sym!r} in kineticLaw of reaction {rxn.sbml_id!r} "
                        f"not resolved (not a species, parameter, local param, "
                        f"compartment, or rule variable)"
                    )
            out[j] = float(cf.fn(*args))
        return out

    def rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """Right-hand-side of the ODE system: dy/dt at (t, y).

        Per-species: amount-mode species use ``dN/dt = stoich @ fluxes``
        directly; concentration-mode species divide by compartment volume.

        Signature matches :func:`scipy.integrate.solve_ivp` and
        :func:`opencell.solvers.ode_scipy.solve_ode_scipy`.
        """
        flux = self.fluxes(t, y)
        dydt = self.stoich @ flux
        # Concentration-mode species: convert substance/time → concentration/time
        for k, sid in enumerate(self.species_ids):
            if self.species_substance_units.get(sid, False):
                continue  # amount-mode: kinetic law already gives dN/dt
            v = self.compartment_volumes[self.species_compartment[sid]]
            if v != 1.0:
                dydt[k] /= v
        return dydt

    # ---- Provenance ----

    def provenance(self) -> dict[str, Any]:
        """Audit record: source file + sha256 + structural shape.

        Use this when persisting simulation outputs so the run can be traced
        back to the exact SBML bytes and model topology.
        """
        return {
            "sbml_path": str(self.sbml_path),
            "sbml_sha256": self.sbml_sha256,
            "sbml_level": self.sbml_level,
            "sbml_version": self.sbml_version,
            "n_dynamic_species": self.n_species,
            "n_reactions": self.n_reactions,
            "n_assignment_rules": len(self.rules),
            "n_global_params": len(self.global_params),
            "n_boundary_species": len(self.boundary_species),
            "compartments": dict(self.compartment_volumes),
        }
