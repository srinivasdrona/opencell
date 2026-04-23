"""Run manifest for reproducibility.

Every simulation run emits a manifest recording exactly what was run:
git SHA, dependency versions, solver config, parameter checksums,
RNG seeds, hardware info, and wall-clock metrics.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunManifest:
    """Reproducibility manifest for a simulation run."""

    timestamp: str = ""
    git_sha: str = ""
    python_version: str = ""
    jax_version: str = ""
    diffrax_version: str = ""
    scipy_version: str = ""
    numpy_version: str = ""
    platform_info: str = ""
    cpu_info: str = ""
    rng_seed: int = 0
    solver_config: dict[str, Any] = field(default_factory=dict)
    parameter_checksum: str = ""
    wall_time_s: float = 0.0
    n_steps: int = 0
    final_time_s: float = 0.0

    @classmethod
    def capture(cls, rng_seed: int = 0, solver_config: dict[str, Any] | None = None) -> RunManifest:
        """Capture current environment into a manifest."""
        import diffrax
        import jax
        import numpy as np
        import scipy

        git_sha = ""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                git_sha = result.stdout.strip()
        except Exception:
            pass

        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            git_sha=git_sha,
            python_version=platform.python_version(),
            jax_version=jax.__version__,
            diffrax_version=diffrax.__version__,
            scipy_version=scipy.__version__,
            numpy_version=np.__version__,
            platform_info=platform.platform(),
            cpu_info=platform.processor(),
            rng_seed=rng_seed,
            solver_config=solver_config or {},
        )

    def save(self, output_dir: str | Path = ".") -> Path:
        """Save manifest to JSON."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = output_dir / f"manifest_{ts}.json"
        with open(filepath, "w") as f:
            json.dump(self.__dict__, f, indent=2)
        return filepath

    @staticmethod
    def checksum_file(filepath: str | Path) -> str:
        """Compute SHA256 checksum of a file."""
        sha = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()
