# Canonical Environment Specification

This document defines the exact reproducible environment for OpenCell development and testing. Use this as the reference baseline when debugging environment-related issues.

**Last Updated:** 2026-04-22

---

## Development Machine

### Hardware
- **CPU:** Intel i7-10700 (8C/16T @ 2.9GHz)
- **RAM:** 64 GB DDR4
- **GPU:** Intel UHD 630 (integrated) — NO CUDA, NO discrete GPU
- **Storage:** E: drive (~930 GB free)

### Operating System
- **OS:** Microsoft Windows 11 Enterprise Insider Preview
- **OS Build:** 26220 (10.0.26220)
- **Build Type:** Multiprocessor Free
- **System:** LENOVO (Model 11EVS09B00)
- **Domain:** fareast.corp.microsoft.com (Microsoft corporate network)
- **Locale:** en-us; English (United States)

### Network Environment
- **Network:** Microsoft corporate network (fareast.corp.microsoft.com)
- **SSL Proxy:** May cause certificate errors with pip/API calls
- **Workaround:** Use trusted hosts flag: `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org`

---

## Python Environment

### Python Interpreter
- **Python Version:** 3.12.10
- **Launcher:** Windows py launcher (`py -3.12`)
- **Installation Method:** Official Python.org MSI or Store app (with py launcher enabled)

### Virtual Environment
- **Directory:** `.venv-opencell` (in project root: `E:\opencell\.venv-opencell`)
- **Naming:** Named explicitly (not generic `.venv`), identifies which project it's for
- **Location:** Same drive as project (E: drive) to avoid path length issues

### Activation (Windows Command Prompt or PowerShell)
```batch
# Command Prompt
E:\opencell\.venv-opencell\Scripts\activate

# PowerShell
E:\opencell\.venv-opencell\Scripts\Activate.ps1
```

### Package Manager
- **Primary:** pip (included with Python)
- **Recommended Upgrade:** Consider switching to `uv` for faster installs and resolution
  - `pip install uv`
  - `uv pip install -e ".[dev]"`

---

## Verified Dependencies (2026-04-22)

All versions listed below have been verified working together on the canonical environment. **Use these exact versions when possible.**

| Package | Version | Notes |
|---------|---------|-------|
| JAX | 0.10.0 | CPU backend only; float64 must be enabled |
| Diffrax | 0.7.2 | ODE/SDE solver library; depends on JAX |
| COBRApy | 0.31.1 | Constraint-based modeling |
| pint | 0.25.3 | Units and quantities |
| SciPy | 1.17.1 | Scientific computing |
| NumPy | 2.4.4 | Numerical arrays |
| libSBML | 5.21.1 (build 52101) | SBML parsing; binary wheels required |
| Biopython | 1.87 | Bioinformatics utilities |
| h5py | 3.16.0 | HDF5 file format support |
| Hypothesis | 6.152.1 | Property-based testing |
| pytest | 8.4.2+ | Test runner |
| pytest-cov | 6.0.0+ | Coverage reporting |
| black | 25.1.0+ | Code formatter |
| ruff | 0.10.0+ | Linter |

### Installation Command
```bash
# From project root
py -3.12 -m venv .venv-opencell
.venv-opencell\Scripts\activate
pip install -e ".[dev]"
```

To install with `uv`:
```bash
pip install uv
uv pip install -e ".[dev]"
```

---

## JAX Configuration

### Mandatory Configuration
JAX must be configured with 64-bit floats enabled in **all simulation code**:

```python
import jax
jax.config.update("jax_enable_x64", True)
```

### Why This Matters
- Default JAX uses 32-bit floats (float32) for performance
- OpenCell simulations require 64-bit precision (float64) for accuracy
- Without this setting, numerical results will diverge significantly
- Set this **before** importing opencell simulation modules

### Backend
- **Backend:** CPU only (no GPU)
- **Reason:** Windows CPU JAX support is less tested than Linux but stable for our use cases
- **Note:** GPU backend available on Colab; see "Acceptable Divergence" section below

### Performance Implications
- CPU execution is slower than GPU, but deterministic and reproducible
- For benchmarks, use the machine as a baseline reference
- For Colab GPU runs, expect 10-100x speedup but accept minor numerical differences

---

## Acceptable Divergence

### When Running on Google Colab (GPU Backend)

JAX GPU execution produces slightly different floating-point results due to non-associative reduction operations:

- **Deterministic Solvers:** Relative error threshold < 1e-6
- **Stochastic Solvers:** Statistical equivalence required (Kolmogorov-Smirnov test, p > 0.01)
- **Root Cause:** GPU floating-point operations are not perfectly associative; CPU ordering differs

### Verification Procedure
```python
import numpy as np
from scipy.stats import ks_2samp

# For deterministic results
rel_error = np.max(np.abs(cpu_result - gpu_result) / (np.abs(cpu_result) + 1e-10))
assert rel_error < 1e-6, f"Relative error {rel_error} exceeds threshold"

# For stochastic results
stat, p_value = ks_2samp(cpu_samples, gpu_samples)
assert p_value > 0.01, f"KS test p-value {p_value} indicates significant difference"
```

---

## Corporate Environment Notes

### Certificate/SSL Issues
- Microsoft corporate network uses SSL proxy
- Pip may fail with certificate verification errors

**Workaround:**
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org package_name
```

Or permanently configure in `%APPDATA%\pip\pip.ini` (Windows):
```ini
[global]
trusted-host = pypi.python.org
               pypi.org
               files.pythonhosted.org
```

### VPN Requirements
- Ensure connected to corporate VPN if accessing internal resources
- Some dependencies may require specific network configuration

---

## Reproducing This Environment

### Quick Start (5 minutes)
```bash
# Navigate to project
cd E:\opencell

# Create virtual environment
py -3.12 -m venv .venv-opencell

# Activate
.venv-opencell\Scripts\activate

# Install package with dev dependencies
pip install -e ".[dev]"

# Verify installation
python -c "import jax; import opencell; print('OK')"
```

### Full Verification (15 minutes)
```bash
# Run tests to verify everything works
pytest tests/ -v --tb=short

# Run a simple simulation
python -c "
import jax
jax.config.update('jax_enable_x64', True)
import opencell
print('Environment verified successfully')
"
```

### Docker (Alternative)
See `E:\opencell\Dockerfile` for containerized environment. Note: Docker on Windows may have different performance characteristics.

---

## Troubleshooting

### "Python 3.12 not found"
- Install from python.org with "Add Python to PATH" enabled
- Or use Windows Store: `winget install Python.Python.3.12`
- Verify with: `py -3.12 --version`

### "JAX import fails"
- Ensure `.venv-opencell` is activated
- On Windows, JAX CPU requires Visual C++ 14.0+: install Visual Studio Build Tools
- Check: `pip list | findstr jax`

### "float64 not working"
- Did you call `jax.config.update("jax_enable_x64", True)` **before** importing JAX?
- Check with: `python -c "import jax; jax.config.update('jax_enable_x64', True); print(jax.numpy.array([1.0]).dtype)"`

### "Stochastic Solvers produce different results"
- Normal on CPU vs GPU (see "Acceptable Divergence" section)
- Use statistical tests (KS test) not exact equality
- Document numerical differences in test reports

### SSL Certificate Errors
- Use `--trusted-host` flags (see "Corporate Environment Notes")
- Check domain: `ping fareast.corp.microsoft.com`
- Verify VPN connection if accessing internal resources

---

## Related Documentation
- **Setup:** See `CONTRIBUTING.md` for development workflow
- **Architecture:** See `docs/architecture/` for system design
- **Decisions:** See `decisions/` for rationale on environment choices
- **Build Info:** Run `systeminfo` for current machine details

---

## Version History

| Date | Change |
|------|--------|
| 2026-04-22 | Initial canonical specification. Python 3.12.10, Windows 11 Build 26220 |
