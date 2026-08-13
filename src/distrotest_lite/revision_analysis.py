from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Callable

from .statistics import ci95, exact_mcnemar_p, wilson


UNRESOLVED_L = {"L_LOG_UNAVAILABLE", "L_LOG_INCOMPLETE_OR_UNPARSABLE"}
P_CATEGORIES = [
    "P_TEST_DECLARED",
    "P_NO_CONVENTIONAL_TEST_DECLARATION_RESOLVED",
    "P_TEST_EXPLICITLY_DISABLED",
    "P_TEST_FILTERED_OR_SUBSETTED",
    "P_TEST_RELOCATED_OR_EMBEDDED",
    "P_UNRESOLVED",
]


def weighted_ratio(
    ids: list[str],
    project: dict[str, dict],
    numerator: Callable[[str], bool],
    denominator: Callable[[str], bool],
) -> float | None:
    num = den = 0.0
    for cid in ids:
        if denominator(cid):
            weight = project[cid]["design_weight"]
            den += weight
            if numerator(cid):
                num += weight
    return num / den if den else None


def stratified_project_bootstrap(
    sample: dict,
    statistic: Callable[[list[str]], float | None],
    seed: int,
    replicates: int = 10_000,
    c2v_only: bool = False,
) -> list[float]:
    rng = random.Random(seed)
    strata: dict[str, list[str]] = defaultdict(list)
    for row in sample["projects"]:
        if not c2v_only or row["stratum"] == "C2V":
            strata[row["stratum"]].append(row["canonical_upstream"])
    values = []
    for _ in range(replicates):
        resample = []
        for stratum in sorted(strata):
            pool = strata[stratum]
            resample.extend(pool[rng.randrange(len(pool))] for _ in range(len(pool)))
        value = statistic(resample)
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def stratified_ratio_fpc(
    sample: dict,
    numerator: Callable[[str], bool],
    denominator: Callable[[str], bool],
) -> dict:
    """Taylor-linearized stratified ratio variance with finite-population correction."""
    rows_by_stratum: dict[str, list[dict]] = defaultdict(list)
    population_by_stratum: dict[str, int] = {}
    for row in sample["projects"]:
        rows_by_stratum[row["stratum"]].append(row)
        population_by_stratum[row["stratum"]] = int(row["stratum_population"])
    estimated_num = estimated_den = 0.0
    for stratum, rows in rows_by_stratum.items():
        population = population_by_stratum[stratum]
        estimated_num += population * sum(
            numerator(row["canonical_upstream"]) and denominator(row["canonical_upstream"])
            for row in rows
        ) / len(rows)
        estimated_den += population * sum(denominator(row["canonical_upstream"]) for row in rows) / len(rows)
    if not estimated_den:
        return {"estimate": None, "standard_error": None, "normal_ci": None}
    estimate = estimated_num / estimated_den
    variance_total = 0.0
    for stratum, rows in rows_by_stratum.items():
        population = population_by_stratum[stratum]
        sample_n = len(rows)
        residuals = [
            float(numerator(row["canonical_upstream"]) and denominator(row["canonical_upstream"]))
            - estimate * float(denominator(row["canonical_upstream"]))
            for row in rows
        ]
        mean = sum(residuals) / sample_n
        sample_variance = sum((value - mean) ** 2 for value in residuals) / (sample_n - 1) if sample_n > 1 else 0.0
        fraction = sample_n / population
        variance_total += population**2 * (1.0 - fraction) * sample_variance / sample_n
    standard_error = math.sqrt(variance_total) / estimated_den
    return {
        "estimate": estimate,
        "standard_error": standard_error,
        "normal_ci": [max(0.0, estimate - 1.959963984540054 * standard_error), min(1.0, estimate + 1.959963984540054 * standard_error)],
        "method": "Taylor-linearized stratified ratio variance with without-replacement finite-population correction",
    }


def analyze_revision(
    sample: dict,
    labels: dict,
    logs: list[dict],
    c2a: dict,
    *,
    seed_base: int = 20260811,
    replicates: int = 10_000,
) -> tuple[dict, dict]:
    project = {row["canonical_upstream"]: row for row in sample["projects"]}
    all_ids = list(project)
    umap = {(row["canonical_upstream"], row["distribution"]): row for row in labels["u"]}
    pmap = {(row["canonical_upstream"], row["distribution"]): row for row in labels["p"]}
    lmap = {(row["canonical_upstream"], row["distribution"]): row for row in labels["l"]}
    logmap = {(row["canonical_upstream"], row["distribution"]): row for row in logs}
    c2a_state = {row["canonical_upstream"]: row["state"] for row in c2a["rows"]}
    bootstrap: dict[str, dict] = {}

    def summarize_ratio(name: str, numerator: Callable[[str], bool], denominator: Callable[[str], bool], seed: int) -> dict:
        eligible = [cid for cid in all_ids if denominator(cid)]
        positive = sum(numerator(cid) for cid in eligible)
        estimate = weighted_ratio(all_ids, project, numerator, denominator)
        values = stratified_project_bootstrap(sample, lambda ids: weighted_ratio(ids, project, numerator, denominator), seed, replicates)
        bootstrap[name] = {"seed": seed, "values": values}
        return {
            "positive_count": positive,
            "denominator": len(eligible),
            "unweighted_proportion": positive / len(eligible) if eligible else None,
            "unweighted_wilson_ci": wilson(positive, len(eligible)),
            "weighted_proportion": estimate,
            "weighted_bootstrap_ci": ci95(values),
            "weighted_fpc_sensitivity": stratified_ratio_fpc(sample, numerator, denominator),
        }

    retrievability = {}
    rq1 = {}
    for index, distro in enumerate(("debian", "fedora")):
        available = lambda cid, d=distro: logmap[(cid, d)]["state"] == "AVAILABLE"
        retrievability[distro] = summarize_ratio(
            f"retrievability_{distro}", available, lambda cid: True, seed_base + index,
        )
        entrypoint = lambda cid, d=distro: umap[(cid, d)]["state"] == "U_TEST_ENTRYPOINT_RESOLVED"
        usable_entrypoint = lambda cid, d=distro: entrypoint(cid) and lmap[(cid, d)]["state"] not in UNRESOLVED_L
        positive = lambda cid, d=distro: lmap[(cid, d)]["state"] == "L_EXECUTION_EVIDENCED"
        rq1[distro] = {
            "conditional": summarize_ratio(f"rq1_conditional_{distro}", positive, usable_entrypoint, seed_base + 10 + index),
            "overall": summarize_ratio(f"rq1_overall_{distro}", positive, entrypoint, seed_base + 20 + index),
            "u_state_counts": dict(Counter(umap[(cid, distro)]["state"] for cid in all_ids)),
        }

    rq2 = {}
    for distro_index, distro in enumerate(("debian", "fedora")):
        positive = lambda cid, d=distro: lmap[(cid, d)]["state"] == "L_EXECUTION_EVIDENCED"
        rows = []
        for category_index, category in enumerate(P_CATEGORIES):
            in_category = lambda cid, d=distro, category=category: category in pmap[(cid, d)]["labels"]
            usable_category = lambda cid, d=distro, membership=in_category: membership(cid) and lmap[(cid, d)]["state"] not in UNRESOLVED_L
            summary = summarize_ratio(
                f"rq2_{distro}_{category}",
                positive,
                usable_category,
                seed_base + 1000 + distro_index * 100 + category_index,
            )
            summary.update(category=category, category_count=sum(in_category(cid) for cid in all_ids))
            rows.append(summary)
        declared = lambda cid, d=distro: "P_TEST_DECLARED" in pmap[(cid, d)]["labels"] and lmap[(cid, d)]["state"] not in UNRESOLVED_L
        nohook = lambda cid, d=distro: "P_NO_CONVENTIONAL_TEST_DECLARATION_RESOLVED" in pmap[(cid, d)]["labels"] and lmap[(cid, d)]["state"] not in UNRESOLVED_L

        def difference(ids: list[str]) -> float | None:
            declared_value = weighted_ratio(ids, project, positive, declared)
            nohook_value = weighted_ratio(ids, project, positive, nohook)
            return None if declared_value is None or nohook_value is None else declared_value - nohook_value

        difference_values = stratified_project_bootstrap(sample, difference, seed_base + 1500 + distro_index, replicates)
        bootstrap[f"rq2_{distro}_declared_minus_nohook"] = {"seed": seed_base + 1500 + distro_index, "values": difference_values}
        rq2[distro] = {
            "rows": rows,
            "declared_minus_nohook_weighted_difference": difference(all_ids),
            "difference_bootstrap_ci": ci95(difference_values),
        }

    c2v_ids = [cid for cid in all_ids if project[cid]["stratum"] == "C2V"]
    strict_ids = [cid for cid in c2v_ids if all(lmap[(cid, distro)]["state"] not in UNRESOLVED_L for distro in ("debian", "fedora"))]

    def paired_state(cid: str) -> str:
        debian = lmap[(cid, "debian")]["state"] == "L_EXECUTION_EVIDENCED"
        fedora = lmap[(cid, "fedora")]["state"] == "L_EXECUTION_EVIDENCED"
        return "both_evidenced" if debian and fedora else "debian_only_evidenced" if debian else "fedora_only_evidenced" if fedora else "neither_positive_evidence"

    counts = Counter(paired_state(cid) for cid in strict_ids)
    counts["one_or_both_unresolved"] = len(c2v_ids) - len(strict_ids)

    def paired_difference(ids: list[str], exact_only: bool = False) -> float | None:
        eligible = [cid for cid in ids if cid in strict_ids and (not exact_only or c2a_state.get(cid) == "C2A_EXACT")]
        if not eligible:
            return None
        return (
            sum(lmap[(cid, "fedora")]["state"] == "L_EXECUTION_EVIDENCED" for cid in eligible)
            - sum(lmap[(cid, "debian")]["state"] == "L_EXECUTION_EVIDENCED" for cid in eligible)
        ) / len(eligible)

    def discordance(ids: list[str], exact_only: bool = False) -> float | None:
        eligible = [cid for cid in ids if cid in strict_ids and (not exact_only or c2a_state.get(cid) == "C2A_EXACT")]
        if not eligible:
            return None
        return sum(paired_state(cid) in {"debian_only_evidenced", "fedora_only_evidenced"} for cid in eligible) / len(eligible)

    difference_values = stratified_project_bootstrap(sample, paired_difference, seed_base + 2000, replicates, c2v_only=True)
    discordance_values = stratified_project_bootstrap(sample, discordance, seed_base + 2001, replicates, c2v_only=True)
    bootstrap["rq3_paired_difference"] = {"seed": seed_base + 2000, "values": difference_values}
    bootstrap["rq3_discordance"] = {"seed": seed_base + 2001, "values": discordance_values}
    discordant_count = counts["debian_only_evidenced"] + counts["fedora_only_evidenced"]
    rq3 = {
        "sampled_c2v_projects": len(c2v_ids),
        "strict_resolved_projects": len(strict_ids),
        "target_strict_projects": 67,
        "counts": dict(counts),
        "directional_discordance_count": discordant_count,
        "discordance_proportion": discordant_count / len(strict_ids),
        "discordance_wilson_ci": wilson(discordant_count, len(strict_ids)),
        "discordance_project_bootstrap_ci": ci95(discordance_values),
        "paired_positive_prevalence_difference_fedora_minus_debian": paired_difference(strict_ids),
        "paired_difference_project_bootstrap_ci": ci95(difference_values),
        "mcnemar_exact_p": exact_mcnemar_p(counts["debian_only_evidenced"], counts["fedora_only_evidenced"]),
    }

    exact_ids = [cid for cid in strict_ids if c2a_state.get(cid) == "C2A_EXACT"]
    exact_difference_values = stratified_project_bootstrap(sample, lambda ids: paired_difference(ids, True), seed_base + 2100, replicates, c2v_only=True)
    exact_discordance_values = stratified_project_bootstrap(sample, lambda ids: discordance(ids, True), seed_base + 2101, replicates, c2v_only=True)
    bootstrap["c2a_paired_difference"] = {"seed": seed_base + 2100, "values": exact_difference_values}
    bootstrap["c2a_discordance"] = {"seed": seed_base + 2101, "values": exact_discordance_values}
    exact_discordant_count = sum(paired_state(cid) in {"debian_only_evidenced", "fedora_only_evidenced"} for cid in exact_ids)
    c2a_result = {
        "identity_states": dict(Counter(c2a_state.values())),
        "strict_exact_primary_artifact_projects": len(exact_ids),
        "directional_discordance_count": exact_discordant_count,
        "discordance_proportion": exact_discordant_count / len(exact_ids) if exact_ids else None,
        "discordance_project_bootstrap_ci": ci95(exact_discordance_values),
        "paired_positive_prevalence_difference_fedora_minus_debian": paired_difference(exact_ids, True),
        "paired_difference_project_bootstrap_ci": ci95(exact_difference_values),
    }

    result = {
        "retrievability": retrievability,
        "rq1": rq1,
        "rq2": rq2,
        "rq3": rq3,
        "c2a": c2a_result,
        "inference": {
            "bootstrap_replicates": replicates,
            "bootstrap_unit": "canonical upstream project, stratified by C2V/non-C2V with Debian/Fedora pairs retained",
            "percentile_quantile_convention": "linear interpolation at p*(n-1)",
            "finite_population_sensitivity": "Taylor-linearized stratified ratio variance with without-replacement FPC",
        },
    }
    return result, bootstrap
