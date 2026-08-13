# Can Official Build Records Reveal Evidence of Package Test Execution?

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21914964.svg)](https://doi.org/10.5281/zenodo.21914964)

## Overview

This repository is the replication package for an empirical study of positive package-test execution evidence in official Debian and Fedora build records. The study separates three measurements: upstream executable test capability (U), downstream packaging test intent (P), and positive qualifying execution evidence in official build records (L). It contains the frozen study inputs, deterministic processing and analysis code, retained validation evidence, and machine-readable results.

## Repository contents

- `src/distrotest_lite/`: repository acquisition, identity resolution, normalization, U/P/L classification, weighting, bootstrap, and RQ1--RQ3 analysis code.
- `src/distrotest_lite_validation/`: independent frame, U, and generic-L validation implementations.
- `scripts/collect/`: collection of normalized package metadata from official services.
- `scripts/prepare/`: corrected-frame reconstruction and release-provenance inventory.
- `scripts/analyze/`: deterministic reproduction of the primary and retained sensitivity analyses.
- `scripts/validate/`: independent automated validation entry points.
- `data/manifests/`: frozen source-index metadata, sample and acquisition manifests, source roles, hashes, URLs, build IDs, and exact-artifact states.
- `data/derived/`: final U/P/L observations and rule-transition records.
- `data/validation/`: machine-readable validation protocols, certificates, comparisons, and frozen output hashes.
- `results/authoritative/`: authoritative primary, sensitivity, and typed result files.

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

## Testing

```bash
uv run pytest -q
```

The released tests cover U/P/L classifiers, repository canonicalization, source-role extraction, weighting and bootstrap behavior, independent validators, and frozen-artifact integrity checks.

## Reproducibility

For identical frozen inputs and the locked environment, the machine-readable primary, sensitivity, and typed outputs are deterministic. Bootstrap sampling uses fixed seeds and resamples canonical upstream projects within the C2V and non-C2V strata while retaining Debian/Fedora pairs.

## Data availability and third-party records

This repository directly distributes normalized package-index metadata, frozen sample and acquisition manifests, official identifiers and URLs, immutable hashes, final derived U/P/L observations, validation certificates, and authoritative result files.

Raw upstream archives, extracted third-party source trees, raw build records, and normalized build logs are intentionally not redistributed. The manifests retain the official locations, exact package/build identities, timestamps, and SHA-256 values needed to retrieve and verify them. This boundary avoids redistributing large provider-controlled artifacts and build records that can contain incidental personal identifiers.

## Citation

The v1.0.0 replication package is archived on Zenodo under the version-specific DOI [10.5281/zenodo.21914964](https://doi.org/10.5281/zenodo.21914964). Use this DOI when citing the archived artifacts. Citation information for the article will be added after publication.
