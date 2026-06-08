from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance


_REPLICATION_STATE_CODES = {
    "idle": 0.0,
    "initiating": 1.0,
    "elongating": 2.0,
    "complete": 3.0,
}
_EVENT_RATE_THRESHOLD = 0.10
_SCALED_DISTANCE_THRESHOLD = 1.0
_EPSILON = 1e-12


def _extract_snapshots(state_after_dict: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    before = state_after_dict.get("before")
    after = state_after_dict.get("after")
    if isinstance(before, dict) and isinstance(after, dict):
        return before, after

    before = state_after_dict.get("state_before")
    after = state_after_dict.get("state_after")
    if isinstance(before, dict) and isinstance(after, dict):
        return before, after

    return None, state_after_dict


def _resolve_path(root: dict[str, Any] | None, dotted_path: str, *, projection_name: str) -> Any:
    if root is None:
        raise KeyError(
            f"Projection '{projection_name}' requires snapshot data, but the requested state is unavailable."
        )

    candidates = [dotted_path]
    if not dotted_path.startswith("chromosome."):
        candidates.insert(0, f"chromosome.{dotted_path}")

    for candidate in candidates:
        current: Any = root
        found = True
        for part in candidate.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found:
            return current

    raise KeyError(
        f"Projection '{projection_name}' could not resolve dotted path '{dotted_path}' in chromosome state."
    )


def _coerce_scalar(value: Any, *, projection_name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        return float(bool(value))
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _REPLICATION_STATE_CODES:
            return _REPLICATION_STATE_CODES[key]
    raise ValueError(f"Projection '{projection_name}' resolved to non-scalar value {value!r}")


def _delta_scalar(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    dotted_path: str,
    *,
    projection_name: str,
) -> float:
    before_value = _coerce_scalar(
        _resolve_path(before, dotted_path, projection_name=projection_name),
        projection_name=projection_name,
    )
    after_value = _coerce_scalar(
        _resolve_path(after, dotted_path, projection_name=projection_name),
        projection_name=projection_name,
    )
    return float(after_value - before_value)


def _delta_len(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    dotted_path: str,
    *,
    projection_name: str,
) -> int:
    before_value = _resolve_path(before, dotted_path, projection_name=projection_name)
    after_value = _resolve_path(after, dotted_path, projection_name=projection_name)
    before_len = len(before_value) if before_value is not None else 0
    after_len = len(after_value) if after_value is not None else 0
    return int(after_len - before_len)


def _default_scale(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    nonzero = np.abs(arr[np.abs(arr) > _EPSILON])
    if nonzero.size == 0:
        return 1.0
    return float(max(np.percentile(nonzero, 95), 1.0))


def extract_projection(state_after_dict: dict[str, Any], projection_spec: list[str] | tuple[str, ...]) -> np.ndarray:
    before, after = _extract_snapshots(state_after_dict)
    components: list[float] = []
    for spec in projection_spec:
        if spec.startswith("delta_"):
            components.append(_delta_scalar(before, after, spec.removeprefix("delta_"), projection_name=spec))
            continue
        if spec == "replication_state":
            value = _resolve_path(after, "replication_state", projection_name=spec)
            components.append(_coerce_scalar(value, projection_name=spec))
            continue
        if spec == "replication_complete_fired_this_tick":
            if before is None:
                after_value = _resolve_path(after, "events.replication_complete", projection_name=spec)
                components.append(float(bool(after_value)))
            else:
                delta = _delta_scalar(before, after, "events.replication_complete", projection_name=spec)
                components.append(float(delta > 0.0))
            continue
        if spec == "repair_event_present":
            delta = _delta_len(before, after, "repair_events_cumulative", projection_name=spec)
            components.append(float(delta > 0))
            continue
        if spec.startswith("repair_count_by_pathway.") and spec.endswith("_delta"):
            pathway = spec.removeprefix("repair_count_by_pathway.").removesuffix("_delta")
            dotted_path = f"repair_count_by_pathway.{pathway}"
            components.append(_delta_scalar(before, after, dotted_path, projection_name=spec))
            continue

        value = _resolve_path(after, spec, projection_name=spec)
        components.append(_coerce_scalar(value, projection_name=spec))
    return np.asarray(components, dtype=np.float64)


def per_component_scaled_distance(
    oc_projections: np.ndarray,
    karr_projections: np.ndarray,
    component_scales: dict[str, float],
) -> dict[str, Any]:
    oc = np.asarray(oc_projections, dtype=np.float64)
    karr = np.asarray(karr_projections, dtype=np.float64)
    if oc.shape != karr.shape:
        raise ValueError(f"Projection tensors must match shape; got {oc.shape} vs {karr.shape}")
    if oc.ndim != 3:
        raise ValueError(f"Expected projection tensors with shape (seed, tick, component); got {oc.shape}")

    component_names = list(component_scales)
    if len(component_names) != oc.shape[2]:
        raise ValueError(
            "component_scales must provide exactly one scale per projection component; "
            f"got {len(component_names)} names for {oc.shape[2]} components"
        )

    payload: dict[str, Any] = {
        "component_raw_w1": {},
        "component_scales": {},
        "component_verdicts": {},
    }
    joint_pass = True
    for idx, component_name in enumerate(component_names):
        scale = float(component_scales[component_name])
        if scale <= 0.0:
            raise ValueError(f"Scale for component '{component_name}' must be positive; got {scale}")
        raw_w1 = float(wasserstein_distance(oc[:, :, idx].reshape(-1), karr[:, :, idx].reshape(-1)))
        scaled_w1 = raw_w1 / max(scale, _EPSILON)
        verdict = "PASS" if scaled_w1 <= _SCALED_DISTANCE_THRESHOLD else "FAIL"
        payload[component_name] = float(scaled_w1)
        payload["component_raw_w1"][component_name] = raw_w1
        payload["component_scales"][component_name] = scale
        payload["component_verdicts"][component_name] = verdict
        joint_pass = joint_pass and verdict == "PASS"
    payload["joint_verdict"] = "PASS" if joint_pass else "FAIL"
    return payload


def hurdle_event_rate_plus_conditional_distance(
    oc_projections: np.ndarray,
    karr_projections: np.ndarray,
) -> dict[str, Any]:
    oc = np.asarray(oc_projections, dtype=np.float64)
    karr = np.asarray(karr_projections, dtype=np.float64)
    if oc.shape != karr.shape:
        raise ValueError(f"Projection tensors must match shape; got {oc.shape} vs {karr.shape}")
    if oc.ndim != 3:
        raise ValueError(f"Expected projection tensors with shape (seed, tick, component); got {oc.shape}")
    if oc.shape[2] < 1:
        raise ValueError("Hurdle distance requires at least one projection component")

    oc_event_mask = oc[:, :, 0].reshape(-1) > 0.0
    karr_event_mask = karr[:, :, 0].reshape(-1) > 0.0
    event_rate_diff = float(abs(np.mean(oc_event_mask) - np.mean(karr_event_mask)))

    conditional_w1: dict[str, float] = {}
    conditional_scaled_w1: dict[str, float] = {}
    conditional_scales: dict[str, float] = {}
    component_verdicts: dict[str, str] = {}
    joint_pass = event_rate_diff <= _EVENT_RATE_THRESHOLD

    for idx in range(1, oc.shape[2]):
        component_name = f"component_{idx}"
        oc_values = oc[:, :, idx].reshape(-1)[oc_event_mask]
        karr_values = karr[:, :, idx].reshape(-1)[karr_event_mask]
        if oc_values.size == 0 and karr_values.size == 0:
            raw_w1 = 0.0
            scale = 1.0
        else:
            raw_w1 = float(wasserstein_distance(oc_values, karr_values))
            scale = _default_scale(karr_values)
        scaled_w1 = raw_w1 / max(scale, _EPSILON)
        verdict = "PASS" if scaled_w1 <= _SCALED_DISTANCE_THRESHOLD else "FAIL"
        conditional_w1[component_name] = raw_w1
        conditional_scaled_w1[component_name] = scaled_w1
        conditional_scales[component_name] = scale
        component_verdicts[component_name] = verdict
        joint_pass = joint_pass and verdict == "PASS"

    return {
        "event_rate_diff": event_rate_diff,
        "event_rate_threshold": _EVENT_RATE_THRESHOLD,
        "conditional_w1_per_component": conditional_w1,
        "conditional_scaled_w1_per_component": conditional_scaled_w1,
        "conditional_component_scales": conditional_scales,
        "component_verdicts": component_verdicts,
        "joint_verdict": "PASS" if joint_pass else "FAIL",
    }


def hurdle_event_rate_plus_conditional_scaled_distance(
    oc_projections: np.ndarray,
    karr_projections: np.ndarray,
) -> dict[str, Any]:
    return hurdle_event_rate_plus_conditional_distance(oc_projections, karr_projections)


__all__ = [
    "extract_projection",
    "hurdle_event_rate_plus_conditional_distance",
    "hurdle_event_rate_plus_conditional_scaled_distance",
    "per_component_scaled_distance",
]
