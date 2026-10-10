# Can Official Build Records Reveal Evidence of Package Test Execution?

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23288389.svg)](https://doi.org/10.5281/zenodo.23288389)

## Overview

This repository is the replication package for an empirical study of positive package-test execution evidence in official Debian and Fedora build records. The study separates three measurements: upstream executable test capability (U), downstream packaging test intent (P), and positive qualifying execution evidence in official build records (L). It contains the frozen study inputs, deterministic processing and analysis code, retained validation evidence, and machine-readable results.

## Repository contents

- `src/distrotest_lite/`: repository acquisition, identity resolution, normalization, U/P/L classification, weighting, bootstrap, and RQ1--RQ3 analysis code.
- `src/distrotest_lite_validation/`: separately implemented frame, U, and generic-L checks.
- `scripts/collect/`: collection of normalized package metadata from official services.
- `scripts/prepare/`: corrected-frame reconstruction and release-provenance inventory.
- `scripts/analyze/`: deterministic reproduction of the primary and retained sensitivity analyses.
- `scripts/validate/`: automated entry points for the separate checks.
- `data/manifests/`: frozen source-index metadata, sample and acquisition manifests, source roles, hashes, URLs, build IDs, and exact-artifact states.
- `data/derived/`: final U/P/L observations and rule-transition records.
- `data/validation/`: machine-readable validation protocols, certificates, comparisons, and frozen output hashes.
- `results/authoritative/`: authoritative primary, sensitivity, and typed result files.
- [DATA_DICTIONARY.md](DATA_DICTIONARY.md): purpose, production stage, structure, and interpretation of every released data file.
- [DATA_SCHEMA.json](DATA_SCHEMA.json): observed nested field types and join keys.
- `data/explanatory/`: complete seven-case primary-disagreement codebook with recipe/log locators.

Generated re-collection data are written under `data/work/`. Reproduced results are written under `results/reproduced/` or `results/recollected/`; these directories are ignored by Git.

## Requirements

- Python 3.12 or newer.
- [`uv`](https://docs.astral.sh/uv/) for the locked Python environment.
- Network access only for live collection from Debian, Fedora, Koji, or Launchpad.
- `dpkg-source`, `rpm`, `rpm2cpio`, and `cpio` when reacquiring and extracting source packages.
- Optional validator tools: Bubblewrap (`bwrap`), Make, CMake/CTest, Meson, Go, Cargo, and Node. CMake, Meson, and pytest are included in the development dependency group.

## Installation

```bash
uv sync --dev
```

## Reproducing the analysis

The default path uses the included frozen derived inputs and does not download the external corpus:

```bash
uv run python scripts/prepare/reconstruct_frame.py
uv run python scripts/analyze/reproduce_results.py
```

The analysis command runs the 10,000-replicate stratified project bootstraps for the primary and retained generic-L sensitivity analyses. It requires the regenerated primary, sensitivity, and typed JSON files to match the authoritative files byte for byte.

## Data collection

Normalized source-package indices can be reacquired from the configured official Debian, Fedora, and Ubuntu repositories:

```bash
uv run python scripts/collect/collect_source_indices.py all
```

The frozen 200-project sample can be reacquired and reclassified with:

```bash
uv run distrotest-lite-full sources --workers 8
uv run distrotest-lite-full logs --workers 12
uv run distrotest-lite-full classify
uv run distrotest-lite-full c2a
uv run distrotest-lite-full ubuntu --workers 6
uv run python scripts/analyze/reproduce_results.py --from-work
```

Debian records are retrieved from official archive metadata and buildd. Fedora source packages and build records are retrieved from official Fedora repositories and Koji. The secondary Ubuntu adapter uses official archive metadata and Launchpad. External historical availability and provider responses can change; a live re-collection is therefore not expected to replace the frozen snapshot silently.

## Outputs

The main analysis writes:

- `scientific_results_primary.json`: RQ1, RQ2, RQ3, weighting, intervals, and exact-artifact sensitivity;
- `scientific_results_posthoc_l_sensitivity.json`: the retained generic-L sensitivity;
- `typed_results.json`: typed values used to check result reporting;
- `bootstrap_primary.json` and `bootstrap_posthoc_l_sensitivity.json`: deterministic bootstrap replicates;
- `reproduction_summary.json`: headline counts and authoritative byte-match status.

## Reproducing the revised figures

The authoritative typed values and frozen primary labels supply the four quantitative manuscript figures. Rendering preserves the original analysis. With the pinned plotting dependency:

```bash
uv run --with matplotlib==3.10.6 python scripts/analyze/render_figures.py
```

PDF, SVG, PNG, and a provenance manifest are written to `results/reproduced/figures/`. Confidence intervals and raw denominators are retained; unresolved U states and paired no-positive states remain visible.

## Testing

```bash
uv run pytest -q
```

The released tests cover U/P/L classifiers, repository canonicalization, source-role extraction, weighting and bootstrap behavior, separate validators, and frozen-artifact integrity checks.

## Reproducibility

U inspects the Debian tree reconstructed by `dpkg-source -x`, which may include distribution patches, and the Fedora tree unpacked from Source0. This source-representation proxy cannot isolate pristine upstream capability independently of distribution modifications. Primary-archive byte comparison uses the declared Debian main orig payload and expanded RPM Source0 separately.

For identical frozen inputs and the locked environment, the machine-readable primary, sensitivity, and typed outputs are deterministic. Bootstrap sampling uses fixed seeds and resamples canonical upstream projects within the C2V and non-C2V strata while retaining Debian/Fedora pairs.

## Data availability and third-party records

This repository directly distributes normalized package-index metadata, frozen sample and acquisition manifests, official identifiers and URLs, immutable hashes, final derived U/P/L observations, validation certificates, and authoritative result files.

Raw upstream archives, extracted third-party source trees, raw build records, and normalized build logs are intentionally not redistributed. The manifests retain the official locations, exact package/build identities, timestamps, and SHA-256 values needed to retrieve and verify them. This boundary avoids redistributing large provider-controlled artifacts and build records that can contain incidental personal identifiers.

## Revision documentation (v1.1.0)

This release documents all 62 JSON/CSV data files in a generated catalogue and supplies the complete paired-disagreement codebook, enriched audit records, historical U-denominator sensitivity, and record-date diagnostics. It preserves the frozen source observations, primary and sensitivity labels, and authoritative numerical results from v1.0.0. A separately versioned token-checker exclusion rejects explicit zero-success counts without changing the retained 194 candidate-set decisions; v1.0 behavior and outputs remain available. To regenerate the structural catalogue:

```bash
uv run python scripts/prepare/generate_data_dictionary.py
```

The 170/30 sample allocation was fixed to prioritize same-version pairs within a 200-project budget. The planning record does not contain a prospective retrieval-rate calculation uniquely deriving that allocation. The 67-usable-pair precision target required 39.4% joint usability from 170 selected projects; 53/170 (31.2%) were usable. The deterministic hash ordering and final weights are retained in the sample manifests. In `data/manifests/sample_revision.json`, top-level `strata` and original manifest hashes retain historical provenance. Corrected stratum populations and weights are in `revision.strata`; corrected inclusion probabilities and design weights are in `projects`. Primary analysis uses `projects[].design_weight`. The data dictionary and structural catalogue explicitly identify these authoritative fields. These additions explain the original design; they preserve its sample and analyses.

To reproduce the added frozen-input diagnostics and checks:

```bash
uv run python scripts/prepare/revision_diagnostics.py
uv run python scripts/analyze/u_correction_sensitivity.py
uv run python scripts/validate/check_token_v1_1.py
```

The official-date metadata can be recollected with `scripts/collect/collect_build_dates.py`; this network operation updates metadata only, and it leaves the frozen log corpus and outcome labels intact. The enriched log audit was unblinded and has no documented independent adjudication. Its historical agreement figures must not be interpreted as calibrated population recall.

## Citation

The v1.1.0 replication release is archived under version-specific DOI [10.5281/zenodo.23288389](https://doi.org/10.5281/zenodo.23288389). Cite that DOI for the revision artifacts.

The archival series uses concept DOI [10.5281/zenodo.21914963](https://doi.org/10.5281/zenodo.21914963), which resolves to its latest version. For immutable version citations, use the version-specific record. The earlier v1.0.0 package remains archived under DOI [10.5281/zenodo.21914964](https://doi.org/10.5281/zenodo.21914964). That earlier DOI identifies the v1.0.0 artifacts. Citation information for the article will be added after publication.
