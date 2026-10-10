#!/usr/bin/env python3
"""Document observed release-file structures without changing empirical inputs."""
from pathlib import Path
from collections import defaultdict
import csv
import json
ROOT=Path(__file__).resolve().parents[2]
PURPOSES={'build_dates_scp_revision.json': ('Record-date metadata for the 194 frozen downloaded official log identities.', 'scripts/collect/collect_build_dates.py: Debian endpoint stamps and official Koji worker/build metadata; no log substitution.'), 'scp_revision_diagnostics.json': ('Frame filters, sample reconstruction, L states/reasons, paired attrition, token counts, and date-gap diagnostics.', 'scripts/prepare/revision_diagnostics.py from frozen inputs and separately collected official date metadata.'), 'log_audit_manifest.json': ('Historical deterministic enriched 89-log audit selection.', 'Stable-hash positive/no-positive selections, all zero cases, and capped new-family coverage after primary L correction.'), 'log_audit_annotations.json': ('Archived within-set visible-evidence annotations for all 89 logs.', 'Unblinded annotation packets displayed automatic labels; assessor identities and independent adjudication are not recorded. Historical recall intervals are not population-calibrated.'), 'study_chronology.json': ('Historical workflow stages and warranted provenance wording.', 'Repository-based chronology distinguishing internal protocol, sampling freeze, generic corrections, primary analysis, and post-hoc trace.'), 'literature_search_2026-08-12.json': ('Targeted positioning queries, included studies, and retrieval limitations.', 'Accessible-web/primary-source search with citation checks on 12-13 August 2026; not a systematic review.'), 'rq1_u_correction_sensitivity.json': ('Historical RQ1 denominator sensitivity before the generic U correction.', 'scripts/analyze/u_correction_sensitivity.py reconstructs old U states from all retained transitions and repeats the same weighted analysis.'), 'token_v1_1_zero_success_check.json': ('Added zero-success exclusions and their effect on retained token candidate sets.', 'scripts/validate/check_token_v1_1.py rechecks v1.0 tokens with the v1.1 exclusion; no change across 194 log decisions and three additional negatives rejected.')}
PURPOSES.update({'p_label_transitions_p-rules-v1.0.0_to_p-rules-v1.1.0.json': ('Complete 400-observation historical P membership transitions.', 'Generic target-body correction after L outcomes were available: 15 Debian observations changed, with 11 disabled and four declared memberships removed.'), 'p_label_transitions_p-rules-v1.0.0_to_p-rules-v1.1.0.csv': ('Tabular historical P transitions with old/new memberships.', 'CSV serialization of the complete P-transition records; exported with LF line endings.'), 'p_transition_matrix_p-rules-v1.0.0_to_p-rules-v1.1.0.json': ('Historical P transition counts for full label sets and individual memberships.', 'Aggregation of the complete non-exclusive P transitions.'), 'rule_amendment_l_v1_2_2.json': ('Historical audit-triggered Meson rule correction and full-sample rerun provenance.', 'Qualifying named-test requirement replaced a bare successful-summary rule before the retained primary analysis; this correction used observed audit content.')})
PURPOSES.update({
'automatic_upl_labels_primary.json': ('Final primary U/P/L observations, keyed by project and distribution.', 'Deterministic source and recipe classifiers plus the frozen primary log classifier; generic U corrections included.'),
'automatic_upl_labels_posthoc_l_sensitivity.json': ('Parallel U/P/L observations with the opt-in generic success-sentence L rule.', 'Primary observations reclassified under the retained generic-L sensitivity; primary labels are preserved.'),
'l_rule_transitions.json': ('Observations whose L state changes in the opt-in sensitivity.', 'Comparison of primary and sensitivity L arrays.'),
'u_label_transitions_v1.1.0_to_v1.2.0.json': ('Complete U state transitions for all source observations.', 'Comparison before and after generic supported-entrypoint correction.'),
'u_label_transitions_v1.1.0_to_v1.2.0.csv': ('Tabular U transitions for reuse in analysis tools.', 'CSV serialization of the retained U-transition records.'),
'u_transition_matrix_v1.1.0_to_v1.2.0.json': ('Counts of U transitions by old and revised state.', 'Aggregation of the complete U-transition records.'),
'c2a_primary_archive.json': ('Selected primary upstream archive hashes and exact-byte comparison states.', 'Debian primary orig archive versus expanded RPM Source0 selection and SHA-256 comparison.'),
'frame_revision.json': ('Corrected matched-frame counts, exclusions, and revision metadata.', 'Rebuilding the homepage-based frame after host-grammar repairs.'),
'log_acquisition.json': ('Exact official build identities, URLs, retrieval states, hashes, and reason codes.', 'Debian buildd and Fedora Koji acquisition adapters under the fixed exact-version/architecture policy.'),
'population_manifest.json': ('Historical frozen repository population and pre-outcome provenance.', 'Population freeze before sample selection; corrected frame is documented separately.'),
'sample_200.json': ('Original frozen sample identities, observations, selection hashes, and design fields.', 'Stratum-wise SHA-256 ordering with the fixed namespace; no replacement after L measurement.'),
'sample_revision.json': ('Same selected projects with corrected-frame probabilities and weights.', 'Reassociation of the unchanged sample with the corrected frame.'),
'source_acquisition_revision.json': ('Source acquisition records after declared-role resolution.', 'Distribution-specific source acquisition and role-based primary-payload selection.'),
'debian_sources.json': ('Normalized Debian source-package index records before matching.', 'Official Sources indices verified against InRelease metadata; latest native source version per name.'),
'fedora_sources.json': ('Normalized Fedora source-RPM metadata before matching.', 'Official repomd/primary metadata; latest native source version per name.'),
'ubuntu_sources.json': ('Normalized Ubuntu metadata for the planned secondary analysis.', 'Official source-index collection; not part of the Debian/Fedora primary population inference.'),
'source_role_selection.json': ('Declared archive roles, selection decisions, and content hashes.', 'Primary source-role resolution rather than filesystem ordering.'),
'ubuntu_secondary.json': ('Secondary Ubuntu acquisition/estimability record.', 'Exact-record secondary procedure; no estimable primary Ubuntu comparison.'),
'rq3_directional_case_traces.json': ('Complete seven-case explanatory trace with primary/sensitivity states and recipe/log locators.', 'Post-hoc inspection of every directional primary disagreement in the 53 strict pairs; labels not overwritten.'),
'rq3_directional_case_traces.csv': ('Tabular version of the seven-case explanatory trace.', 'Serialization of the same complete explanatory case set.'),
'automated_validation_protocol.json': ('Rules and scope for automated validation.', 'Protocol freeze before independent validation comparisons.'),
'deterministic_run_1_hashes.json': ('Output hashes from the first clean deterministic execution.', 'SHA-256 inventory after the first recorded validation run.'),
'deterministic_run_2_hashes.json': ('Output hashes from the second clean deterministic execution.', 'SHA-256 inventory after the second recorded validation run.'),
'frame_collision_report.json': ('Canonical-key collision and ambiguity diagnostics.', 'Deterministic corrected-frame collision check.'),
'frame_independent_validation.json': ('Independently implemented URL identity results.', 'Host-specific identity grammar implementation in distrotest_lite_validation.'),
'frame_production_vs_independent.json': ('Agreement and discrepancies between frame identity implementations.', 'Join and comparison by original record identity; agreement is not reference-based matching accuracy.'),
'l_sensitivity_adversarial_results.json': ('Generic-L rule checks against deterministic adversarial negatives.', 'Execution of negation, zero, collection, compilation, and related negative fixtures.'),
'l_sensitivity_candidates.json': ('Logs affected by the generic-L sensitivity.', 'Corpus scan and comparison against frozen primary L states.'),
'l_sensitivity_independent_validation.json': ('Independent token-based generic-success checks.', 'Separately implemented test/result/count token logic with exclusion contexts.'),
'l_sensitivity_production_vs_independent.json': ('Comparison of generic-L production and independent token checks.', 'Join of corpus-wide automated outputs; no human reference labels supplied.'),
'l_sensitivity_validation_manifest.json': ('Input identities, hashes, and scope of the L sensitivity check.', 'Frozen validation input/output provenance inventory.'),
'production_comparison_provenance.json': ('Provenance of classifier outputs used for validation comparisons.', 'Explicit production-input identity and hash inventory.'),
'u88_blind_input.json': ('Frozen 88-case U validation inputs without production labels.', 'Deterministic label-blind validation-set preparation.'),
'u88_production_comparison.json': ('Production U comparisons for the initial 88-case exercise.', 'Join of frozen production and independent U outputs.'),
'u88_validation_consensus.json': ('Agreement, disagreement, and indeterminate states of the initial two U paths.', 'Comparison of native discovery and structured static inspection; indeterminate is not a negative reference.'),
'u88_validator_a.json': ('Bounded offline native-discovery U outputs.', 'First independently implemented automated validation path.'),
'u88_validator_b.json': ('Structured static-inspection U outputs.', 'Second independently implemented automated validation path.'),
'u_corrected_production_assessment.json': ('Assessment of final U positives after generic corrections.', 'Combination of original positive certificates and supported counterexample certificates.'),
'u_nonpositive_counterexample_search.json': ('Supported-domain missed entrypoints among original nonpositive U observations.', 'Label-blind counterexample search followed by production comparison; no exhaustive absence claim.'),
'u_positive_certificates.json': ('Artifact-linked evidence for production-positive U eligibility claims.', 'Independent automated native/static checks with supporting file/target evidence.'),
'u_positive_output_freeze.json': ('Frozen positive-validation output hashes and provenance.', 'Hash inventory of completed positive validation outputs.'),
'u_positive_validation_protocol.json': ('State-specific positive-claim validation scope and rules.', 'Protocol for checking original positives and searching supported nonpositive cases.'),
'u_positive_validation_summary.json': ('Positive-certification and supported-miss summary counts.', 'Aggregation of retained certificates and counterexample search.'),
'u_validation_manifest.json': ('U validation case identities and input hashes.', 'Frozen manifest for automated U checks.'),
'validation_implementation_freeze.json': ('Independent-validation implementation identities and hashes.', 'Code inventory frozen for the automated validation exercise.'),
'validation_outputs_freeze.json': ('Validation-output identities and hashes.', 'Content-hash inventory after completed validation.'),
'scientific_results_primary.json': ('Authoritative primary RQ1/RQ2/RQ3 estimates, intervals, and archive subset results.', 'scripts/analyze/reproduce_results.py from frozen corrected-frame sample and primary U/P/L observations.'),
'scientific_results_posthoc_l_sensitivity.json': ('Authoritative secondary generic-L sensitivity estimates.', 'Same analysis pipeline with the separate opt-in sensitivity labels.'),
 'typed_results.json': ('Typed reported values with numerator, denominator, interval method, and weighting fields.', 'Typed reporting extraction from authoritative primary and sensitivity analysis.'),
'release_manifest.json': ('Release-file content hashes and distribution boundary.', 'Inventory of distributable package files; does not hash itself.'),
})

def kind(v):
    return 'null' if v is None else 'boolean' if isinstance(v,bool) else 'integer' if isinstance(v,int) else 'number' if isinstance(v,float) else 'string' if isinstance(v,str) else 'array' if isinstance(v,list) else 'object'

def schema(value):
    types=defaultdict(set)
    def walk(v,path):
        types[path].add(kind(v))
        if isinstance(v,dict):
            for k,x in v.items(): walk(x,path+'.'+k)
        elif isinstance(v,list):
            for x in v: walk(x,path+'[]')
    walk(value,'$')
    return {p:sorted(t) for p,t in sorted(types.items())}

entries=[]
for parent in ('data','results/authoritative'):
    for p in sorted((ROOT/parent).rglob('*')):
        if p.is_file() and p.suffix in ('.json','.csv'):
            entries.append(p)
entries.append(ROOT/'results/release_manifest.json')
records=[]
for p in entries:
    purpose,producer=PURPOSES[p.name]
    if p.suffix=='.json':
        value=json.loads(p.read_text()); observed=schema(value)
        shape='object: '+', '.join(value.keys()) if isinstance(value,dict) else f'array ({len(value)} records)'
    else:
        with p.open(newline='') as f: reader=csv.DictReader(f); cols=reader.fieldnames; rows=list(reader)
        observed={c:['string'] for c in cols};shape=f'CSV ({len(rows)} rows): '+', '.join(cols)
    records.append({'path':str(p.relative_to(ROOT)),'purpose':purpose,'creation':producer,'structure':shape,'observed_field_types':observed})
output={'schema_version':'1.0','schema_status':'Observed structural inventory, not a normative JSON Schema; missing keys and empty arrays do not establish required fields or item types.',
        'join_keys':['canonical_upstream','distribution'], 'files':records}
(ROOT/'DATA_SCHEMA.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
lines=['# Released data dictionary','',
'For each released JSON or CSV data file, this catalogue gives its purpose, production stage, and structure. [DATA_SCHEMA.json](DATA_SCHEMA.json) lists observed field types, including nested paths (`[]` denotes array items). The frozen files are read by `scripts/prepare/generate_data_dictionary.py`. Its structural inventory preserves optional keys, nulls, and empty arrays without defining a normative schema.','',
'`canonical_upstream` identifies a normalized upstream project; `distribution` identifies its Debian or Fedora observation. Join on both fields when present. Package versions and NVRs identify distribution artifacts, while SHA-256 fields identify exact content. URL/task identifiers support reacquisition; local evidence paths refer to the original normalized acquisition layout and are locators, not redistributed raw files. Join the seven-case codebook to acquisition manifests using project and distribution to resolve official URLs, task IDs, and hashes.','',
'U states distinguish executable entrypoints, assets, supported absence, and unresolved semantics. P categories overlap and are not additive. L states distinguish visible positives, explicit zero-test output, usable logs without positives, incomplete logs, and unavailable logs. Missing evidence is not historical non-execution. Confidence intervals and weights must be interpreted using each result row\'s method and weighting fields; sparse-zero Wilson bounds are unweighted.','',
'The historical token checker is named `token_semantic_success_validator_v1.0` in machine-readable records. The separately versioned v1.1 exclusion rejects zero-success counts when nonzero skip counts or timings could mislead v1.0. The original entry points and records are retained.', '', 'The log audit selected cases using classifier outputs and displayed those outputs during annotation. Its perfect within-set agreement does not supply a calibrated population recall interval; no independently adjudicated assessor labels are documented.', '', 'Record dates describe the selected historical official builds, which can be years apart. Same-version and exact-archive pairing leave toolchain and time effects uncontrolled. Retrieval failure codes refer to the specified architecture and version policy rather than every possible official record.', '', 'Historical manifests and validation stages are retained for provenance. The corrected sample and final primary labels drive the authoritative primary results. Sensitivity labels and results remain secondary. Automated validation agreement is not independent human ground truth. Ubuntu records document the planned secondary analysis and do not support primary Ubuntu inference.','']
for r in records:
    lines += ['## `'+r['path']+'`','',r['purpose'],'','Created by: '+r['creation'],'','Structure: `'+r['structure']+'`. Full observed field types are in `DATA_SCHEMA.json`.','']
(ROOT/'DATA_DICTIONARY.md').write_text('\n'.join(lines))
print(f'Documented {len(records)} files')
