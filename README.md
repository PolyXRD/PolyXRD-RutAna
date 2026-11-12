# PolyXRD RutAna

**A dedicated determination tool for GB/T 30793—2014 "X-ray Diffraction Method for Determining the Anatase/Rutile Ratio in Titanium Dioxide Pigments".**

PolyXRD family members: PolyXRD (data analysis) · PolyXRD-Converter (format conversion) ·
PolyXRD-SynthPattern (pattern synthesis) · PolyXRD-CifCalc (CIF tools) · **RutAna (this project, crystal-form ratio determination)**.

## What this is

RutAna does exactly one thing: per GB/T 30793—2014 it delivers compliant, reproducible,
report-ready determination of the anatase/rutile ratio.

- **Method A (intensity-ratio method)**: measures the net peak intensities of anatase (101) 25.30°
  and rutile (110) 27.44° (Cu Kα), `w_a = 1/(1 + K·I_r/I_a) × 100%`; K is calibrated by
  multi-point calibration with ≥3 standard mixture points (default: least squares through the origin,
  `K = Σxy/Σx²`), with an alarm when R² < 0.995.
- **Method B (Rietveld full-pattern fitting method)**: 5–90° full-pattern fitting (variable
  projection: scale + Chebyshev background solved linearly, zero/U,V,W/η nonlinear LM), with built-in
  anatase/rutile CIFs (COD 7206075 / 9001681), Hill–Howard quantification `W_p ∝ S·Z·M·V`,
  algorithm acceptance criterion **Rwp ≤ 10%** (golden baseline, not a UI verdict tier). Virtual-sample
  round-trip: Rwp 2.1–3.5%, recovery error ≤0.09pp.
- **Method B result verdict (v1.6.2, four tiers)**: Rwp < 10% very good fit (green); 10–15% good fit
  (blue); 15–20% acceptable fit (amber); > 20% poor fit (red). The thresholds have a single source,
  `rutana/gui/verdict.py`; the single-sample result card, batch CSV and HTML report use the same wording.
- **Method B preferred-orientation (March–Dollase) refinement** (v1.4.0, enabled by default): refines
  each phase's preferred-orientation parameter r per `W = (r²cos²α + r⁻¹sin²α)^(−3/2)` (anatase default
  preferred plane (001), rutile (110), bounds 0.2–5.0; r=1 means no preferred orientation). The
  peak-enumeration cache key excludes r, and the forward pass cheaply reweights by detail, so
  single-sample time is on the same order as with it off; real data from four samples confirms Rwp
  does not degrade, with worst-case quantitative relative error 2.85% (see
  docs/VALIDATION_v1.0.0.md §v1.4.0).
- **Splash screen** (v1.4.0): PyInstaller bootloader splash — shows the branding splash image during
  the onefile extraction phase (a few seconds of cold start), then closes automatically once the main
  window is ready, solving the problem of the exe showing no window for >6s on cold start.
- **Main-peak parameter table (v1.7.0)**: a persistent table below the pattern, listing from the
  built-in CIFs the 2θ, d, (hkl), net peak height, FWHM and Scherrer crystallite size of the top 5
  main peaks of anatase/rutile (`D = Kλ/(β·cosθ)`, K = 0.9; FWHM is not corrected for instrumental
  broadening, so it is an apparent value / lower bound). Values come from the measured pattern (the
  same V100 background protocol as Method A) and refresh on import or pattern switch; when an
  overlapping peak cannot be measured with the wide window it automatically narrows to 0.25° and
  retries, and if still unmeasurable the row is left showing "—".
- **Method B refined structure results (v1.7.1)**: the Method B panel shows, below the R-factor card,
  each phase's **refined** cell parameters, cell volume and Scherrer crystallite size of that phase's
  strongest peak; the "More Info…" window gives the full refined results (the six cell parameters and
  volume, per-phase scale / strongest-peak 2θ / FWHM / crystallite size / preferred-orientation r,
  global Caglioti U/V/W, eta, asymmetry, temperature factor, iterations and restart / dropped-phase
  information).
- The result is the **relative ratio of the two crystal phases**, excluding amorphous coatings (the
  Al/Si/Zr coatings of TiO₂ pigments are not included in the result).

Core modules: `rutana/core/` (patterns reading · background · peakmeasure net peaks ·
method_a K calibration and results · smooth optional smoothing · plot drawing · profile/ forward model ·
refine/ refinement engine and QPA); CLI: `rutana/cli/rutana.py`;
GUI (PySide6, Chinese / English / Japanese): `rutana/gui/`;
virtual laboratory and benchmarks: `tools/gen_virtual.py`, `tools/bench.py`, `tools/bench_b.py`.

## Supported diffraction pattern formats

Starting with v1.6.0, "Open Pattern" and "Add Folder" support the following formats:

- Generic text and FullProf: `.xy`, `.txt`, `.dat`, `.csv`, `.smz` (including two-column, FullProf `pd`, Shimadzu ASCII and Jade two-line headers);
- Multi-vendor binary RAW: `.raw`, plus `.org`, `.rsm`, `.rbg`, `.rk1`, `.rax`, `.rlz`, `.rfi` from the same Shimadzu container;
- MDI/Jade: `.mdi`; GSAS: `.gsas`, `.gss`, `.gsa`, `.gda`, `.fxye`;
- Rigaku: `.ras`, `.rasx`; Topas/generic: `.xye`, `.qye`; Fit2D: `.chi`, `.qchi`;
- XML/compressed containers: `.xrdml`, `.xml`, `.brml`; pattern JSON: `.json`.

The pattern reader reuses **PolyXRD-Converter**'s format-detection and parsing implementation,
shipped with RutAna as a vendor copy, without importing the sibling repository at runtime. RAW is
auto-detected by file-header magic for Rigaku RINT, Scintag RAW2, Bruker/Siemens v1 and Shimadzu
private containers; if the file header cannot give a trustworthy 2θ axis, the software explicitly
refuses and prompts you to export to a text format from the instrument software first, never faking
an angle axis from point indices.

### CLI usage

```bash
# Known K value
D:/Project/XRD/python310/python.exe -m rutana.cli.rutana a-method \
    --sample tests/data/virtual/v50.xy --K 1.0 --json out.json

# On-site calibration from 3 calibration mixtures (file:mass ratio)
D:/Project/XRD/python310/python.exe -m rutana.cli.rutana a-method \
    --sample sample.xy --calib c25.xy:0.3333 c50.xy:1.0 c75.xy:3.0 \
    --repeat sample_2nd.xy --json out.json --png spectrum.png
```

### GUI startup

```bash
D:/Project/XRD/python310/python.exe -m rutana.gui
```

## Editions and registration (v1.5.0)

RutAna has two editions, fixed at build time (`rutana/edition.py`) and read-only at runtime:

| | Registered edition (Setup installer) | Internal evaluation build (single-file exe) |
|---|---|---|
| Artifact | `PolyXRD-RutAna-vX.Y.Z-Setup.exe` | `PolyXRD-RutAna-vX.Y.Z.exe` |
| Registration mechanism | ✅ (includes `rutana.gui.registration`) | ❌ (fully excluded by spec excludes) |
| Unregistered startup | Every launch pops up "This software is unregistered. All rights reserved. Commercial use is prohibited. To register, please contact sshztx@outlook.com"; click "OK" to continue using it normally, click "Enter Registration Code" to register and it will no longer prompt | — |
| Help menu | includes "Enter Registration Code (&R)…" | no registration items |
| Status bar | rightmost: when registered shows the registered "unit/department name", when unregistered shows "Unregistered" | **centered**, showing "Internal Evaluation Build" (red, bold) |

- **Registration code**: generated by the developer from the "unit/department name" provided by the
  user (offline HMAC-SHA256, interoperable with the PolyXRD family's code-generation tool).
  **To register, please contact sshztx@outlook.com**; just tell us the unit/department name to obtain
  the registration code, then paste it in the software under "Help → Enter Registration Code".
- **Developer-side code generation**: use PolyXRD-Reg's `dist\PolyXRD-RegTool.exe` (GUI version)
  or `make_reg_code.py` (command line); see `D:\Project\XRD\PolyXRD-Reg\README.md` for details.
- **Registration status file**: `%APPDATA%\PolyXRD\Registration\PolyXRD_RutAna.json`; the
  registration code is re-validated on every startup, and hand-editing the JSON to fake "Registered"
  has no effect; uninstalling the software does not delete this file, so registration survives a
  reinstall.
- Build: internal evaluation build `build_exe.bat`; registered edition `build_setup.bat`
  (PyInstaller onedir + Inno Setup installer, with selectable install location, Start Menu / Desktop
  shortcuts, and uninstall support). The GitHub Release provides the Setup installer version.

## How to run pytest

```bash
cd /d/Project/XRD/PolyXRD-RutAna && D:/Project/XRD/python310/python.exe -m pytest -q
```

Dependency lockfile: `requirements.txt` (numpy 2.2.6 / scipy 1.15.3 / matplotlib 3.10.9 /
PySide6 6.11.2 / pytest). Virtual-sample benchmark data is generated by `tools/gen_virtual.py`
(seed=20260701, reproducible):

```bash
D:/Project/XRD/python310/python.exe tools/gen_virtual.py --out tests/data/virtual
D:/Project/XRD/python310/python.exe tools/bench.py --method a    # Method A 8-ratio round-trip
D:/Project/XRD/python310/python.exe tools/bench_b.py             # Method B 8-ratio round-trip
```

> **Convention note**: the Method A golden baseline `tests/golden/method_a_roundtrip.json` is frozen
> from the **narrow-window pattern** `v50.xy` (the Method B baseline corresponds to the wide-scan
> patterns in `tests/data/virtual_b/`). `v50_wide.xy` uses a different noise implementation, so
> results may differ from the narrow-window baseline by ~0.02pp; for bit-for-bit comparison use the
> corresponding pattern source.

## Task progress table

| Card | Content | Status |
|---|---|---|
| T0.1 | repository skeleton and dependency lock | ✅ |
| T0.2 | verbatim freeze of standard clauses (STD_FREEZE.md) | ✅ (repeatability limit corrected to 0.18% per the original text of §9.1) |
| T0.3 | core data types dtypes | ✅ |
| T1.1 | pattern reader patterns | ✅ |
| T1.2 | virtual laboratory gen_virtual | ✅ |
| T1.3 | pattern plotting plot | ✅ |
| T2.1–T2.7 | full Method A chain (background / net peaks / K calibration / results / benchmark / CLI / smoothing) | ✅ |
| T3.1–T3.3 | Method B forward model + built-in CIFs | ✅ |
| T4.1–T4.6, T4.8 | Method B refinement engine + QPA + performance | ✅ |
| T4.7 | cell / preferred-orientation refinement | ✅ (v1.0.0: per-phase a,c scale refinement; v1.4.0: March–Dollase preferred-orientation r refinement, on by default) |
| T5.x | compliance verdict / report export / ledger | ✅ (GUI exports HTML/CSV/PNG) |
| T6.x | PySide6 GUI + trilingual i18n + About/Copyright | ✅ |
| T7.x | two QA regression rounds + packaging verification | ✅ (real-sample L3 cross-validation pending experiment scheduling) |

## License

Dual license (Academic / Commercial), see `LICENSE` and `LICENSE-CN`.
Commercial contact: sshztx@outlook.com · https://github.com/PolyXRD
