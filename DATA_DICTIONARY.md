# Released data dictionary

For each released JSON or CSV data file, this catalogue gives its purpose, production stage, and structure. [DATA_SCHEMA.json](DATA_SCHEMA.json) lists observed field types, including nested paths (`[]` denotes array items). The frozen files are read by `scripts/prepare/generate_data_dictionary.py`. Its structural inventory preserves optional keys, nulls, and empty arrays without defining a normative schema.

`canonical_upstream` identifies a normalized upstream project; `distribution` identifies its Debian or Fedora observation. Join on both fields when present. Package versions and NVRs identify distribution artifacts, while SHA-256 fields identify exact content. URL/task identifiers support reacquisition; local evidence paths refer to the original normalized acquisition layout and are locators, not redistributed raw files. Join the seven-case codebook to acquisition manifests using project and distribution to resolve official URLs, task IDs, and hashes.

U states distinguish executable entrypoints, assets, supported absence, and unresolved semantics. P categories overlap and are not additive. L states distinguish visible positives, explicit zero-test output, usable logs without positives, incomplete logs, and unavailable logs. Missing evidence is not historical non-execution. Confidence intervals and weights must be interpreted using each result row's method and weighting fields; sparse-zero Wilson bounds are unweighted.

The historical token checker is named `token_semantic_success_validator_v1.0` in machine-readable records. The separately versioned v1.1 exclusion rejects zero-success counts when nonzero skip counts or timings could mislead v1.0. The original entry points and records are retained.

The log audit selected cases using classifier outputs and displayed those outputs during annotation. Its perfect within-set agreement does not supply a calibrated population recall interval; no independently adjudicated assessor labels are documented.

Record dates describe the selected historical official builds, which can be years apart. Same-version and exact-archive pairing leave toolchain and time effects uncontrolled. Retrieval failure codes refer to the specified architecture and version policy rather than every possible official record.

Historical manifests and validation stages are retained for provenance. The corrected sample and final primary labels drive the authoritative primary results. Sensitivity labels and results remain secondary. Automated validation agreement is not independent human ground truth. Ubuntu records document the planned secondary analysis and do not support primary Ubuntu inference.

## `data/derived/automatic_upl_labels_posthoc_l_sensitivity.json`

Parallel U/P/L observations with the opt-in generic success-sentence L rule.

Created by: Primary observations reclassified under the retained generic-L sensitivity; primary labels are preserved.

Structure: `object: l, p, rule_versions, u`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/derived/automatic_upl_labels_primary.json`

Final primary U/P/L observations, keyed by project and distribution.

Created by: Deterministic source and recipe classifiers plus the frozen primary log classifier; generic U corrections included.

Structure: `object: l, p, rule_versions, u`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/derived/l_rule_transitions.json`

Observations whose L state changes in the opt-in sensitivity.

Created by: Comparison of primary and sensitivity L arrays.

Structure: `array (1 records)`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/derived/u_label_transitions_v1.1.0_to_v1.2.0.csv`

Tabular U transitions for reuse in analysis tools.

Created by: CSV serialization of the retained U-transition records.

Structure: `CSV (400 rows): canonical_upstream, distribution, old_state, new_state, old_family, new_family, changed, new_rule_ids`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/derived/u_label_transitions_v1.1.0_to_v1.2.0.json`

Complete U state transitions for all source observations.

Created by: Comparison before and after generic supported-entrypoint correction.

Structure: `object: changed_count, new_rule_version, observation_count, old_rule_version, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/derived/u_transition_matrix_v1.1.0_to_v1.2.0.json`

Counts of U transitions by old and revised state.

Created by: Aggregation of the complete U-transition records.

Structure: `object: matrix, new_rule_version, old_rule_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/explanatory/rq3_directional_case_traces.csv`

Tabular version of the seven-case explanatory trace.

Created by: Serialization of the same complete explanatory case set.

Structure: `CSV (7 rows): canonical_upstream, primary_direction, artifact_state, mechanism_class, measurement_sensitivity_case, interpretation`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/explanatory/rq3_directional_case_traces.json`

Complete seven-case explanatory trace with primary/sensitivity states and recipe/log locators.

Created by: Post-hoc inspection of every directional primary disagreement in the 53 strict pairs; labels not overwritten.

Structure: `object: review_scope, review_type, primary_counts, trace_sensitivity_counts, trace_sensitivity_discordance, trace_sensitivity_fedora_minus_debian, trace_sensitivity_exact_artifact_discordance, trace_sensitivity_exact_artifact_fedora_minus_debian, trace_sensitivity_debian_declared, cases`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/build_dates_scp_revision.json`

Record-date metadata for the 194 frozen downloaded official log identities.

Created by: scripts/collect/collect_build_dates.py: Debian endpoint stamps and official Koji worker/build metadata; no log substitution.

Structure: `object: collected_at_utc, scope, interpretation, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/c2a_primary_archive.json`

Selected primary upstream archive hashes and exact-byte comparison states.

Created by: Debian primary orig archive versus expanded RPM Source0 selection and SHA-256 comparison.

Structure: `object: identity_rule, rows`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/frame_revision.json`

Corrected matched-frame counts, exclusions, and revision metadata.

Created by: Rebuilding the homepage-based frame after host-grammar repairs.

Structure: `object: added_resolved_projects, additions, method_version, old, removed_resolved_projects, revised, sample_added, sample_removed, source_indices`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/log_acquisition.json`

Exact official build identities, URLs, retrieval states, hashes, and reason codes.

Created by: Debian buildd and Fedora Koji acquisition adapters under the fixed exact-version/architecture policy.

Structure: `object: completed_at, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/population_manifest.json`

Historical frozen repository population and pre-outcome provenance.

Created by: Population freeze before sample selection; corrected frame is documented separately.

Structure: `object: input_frame_sha256, namespace, project_count, projects, selection_method`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/sample_200.json`

Original frozen sample identities, observations, selection hashes, and design fields.

Created by: Stratum-wise SHA-256 ordering with the fixed namespace; no replacement after L measurement.

Structure: `object: frozen_at, input_frame_sha256, namespace, population_manifest_sha256, projects, selected_project_count, selection_method, strata`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/sample_revision.json`

Same selected projects with corrected-frame probabilities and weights.

Created by: Reassociation of the unchanged sample with the corrected frame.

Structure: `object: frozen_at, input_frame_sha256, namespace, population_manifest_sha256, projects, revision, selected_project_count, selection_method, strata`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/source_acquisition_revision.json`

Source acquisition records after declared-role resolution.

Created by: Distribution-specific source acquisition and role-based primary-payload selection.

Structure: `object: records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/source_indices/debian_sources.json`

Normalized Debian source-package index records before matching.

Created by: Official Sources indices verified against InRelease metadata; latest native source version per name.

Structure: `object: created_at, distribution, index_reasons, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/source_indices/fedora_sources.json`

Normalized Fedora source-RPM metadata before matching.

Created by: Official repomd/primary metadata; latest native source version per name.

Structure: `object: created_at, distribution, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/source_indices/ubuntu_sources.json`

Normalized Ubuntu metadata for the planned secondary analysis.

Created by: Official source-index collection; not part of the Debian/Fedora primary population inference.

Structure: `object: created_at, distribution, index_reasons, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/source_role_selection.json`

Declared archive roles, selection decisions, and content hashes.

Created by: Primary source-role resolution rather than filesystem ordering.

Structure: `object: records, rule`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/manifests/ubuntu_secondary.json`

Secondary Ubuntu acquisition/estimability record.

Created by: Exact-record secondary procedure; no estimable primary Ubuntu comparison.

Structure: `object: available_logs, completed_at, records, state`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/automated_validation_protocol.json`

Rules and scope for automated validation.

Created by: Protocol freeze before independent validation comparisons.

Structure: `object: schema_version, protocol_id, author_amendment_date, status, supersedes, independence_definition, u_selection, prohibited_validator_inputs, validator_a, validator_b, consensus_rules, freeze_order, correction_rule, future_hash_manifest, future_output_hash_manifest`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/deterministic_run_1_hashes.json`

Output hashes from the first clean deterministic execution.

Created by: SHA-256 inventory after the first recorded validation run.

Structure: `object: file_count, files, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/deterministic_run_2_hashes.json`

Output hashes from the second clean deterministic execution.

Created by: SHA-256 inventory after the second recorded validation run.

Structure: `object: file_count, files, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/frame_collision_report.json`

Canonical-key collision and ambiguity diagnostics.

Created by: Deterministic corrected-frame collision check.

Structure: `object: collision_count, collisions, retained_matched_projects, schema_version, shared_identities`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/frame_independent_validation.json`

Independently implemented URL identity results.

Created by: Host-specific identity grammar implementation in distrotest_lite_validation.

Structure: `object: excluded_ambiguous_identity_count, implementation, input_counts, records, resolved_url_count, retained_matched_project_count, schema_version, shared_identity_count, unresolved_url_count`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/frame_production_vs_independent.json`

Agreement and discrepancies between frame identity implementations.

Created by: Join and comparison by original record identity; agreement is not reference-based matching accuracy.

Structure: `object: both_resolved_url_count, disagreement_mechanisms, disagreements, identity_agreement_count, identity_disagreement_count, independent_implementation_agreement, independent_retained_matched_project_count, production_retained_matched_project_count, retained_only_independent, retained_only_production, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/l_sensitivity_adversarial_results.json`

Generic-L rule checks against deterministic adversarial negatives.

Created by: Execution of negation, zero, collection, compilation, and related negative fixtures.

Structure: `object: fixture_count, records, rejected_count, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/l_sensitivity_candidates.json`

Logs affected by the generic-L sensitivity.

Created by: Corpus scan and comparison against frozen primary L states.

Structure: `object: candidate_log_count, records, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/l_sensitivity_independent_validation.json`

Independent token-based generic-success checks.

Created by: Separately implemented test/result/count token logic with exclusion contexts.

Structure: `object: certificates, corpus_count, positive_log_count, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/l_sensitivity_production_vs_independent.json`

Comparison of generic-L production and independent token checks.

Created by: Join of corpus-wide automated outputs; no human reference labels supplied.

Structure: `object: corpus_count, generic_rule_independently_confirmed, generic_rule_not_confirmed, generic_rule_positive_count, records, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/l_sensitivity_validation_manifest.json`

Input identities, hashes, and scope of the L sensitivity check.

Created by: Frozen validation input/output provenance inventory.

Structure: `object: records, rule, scope, status, validation_artifact`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/literature_search_2026-08-12.json`

Targeted positioning queries, included studies, and retrieval limitations.

Created by: Accessible-web/primary-source search with citation checks on 12-13 August 2026; not a systematic review.

Structure: `object: schema_version, search_date_utc, positioning_closed_utc, capabilities, capabilities_record_status, closure_amendment, queries, screening_rule, included_or_reverified, official_mechanism_sources, excluded_examples, novelty_assessment`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/log_audit_annotations.json`

Archived within-set visible-evidence annotations for all 89 logs.

Created by: Unblinded annotation packets displayed automatic labels; assessor identities and independent adjudication are not recorded. Historical recall intervals are not population-calibrated.

Structure: `object: annotation_scope, manifest_sha256, reviewed_audit_ids, false_positive_audit_ids, missed_visible_positive_audit_ids, visible_zero_test_evidence_audit_ids, systematic_defect, notes`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/log_audit_manifest.json`

Historical deterministic enriched 89-log audit selection.

Created by: Stable-hash positive/no-positive selections, all zero cases, and capped new-family coverage after primary L correction.

Structure: `object: automatic_labels_sha256, created_at, namespace, new_family_cap, newly_encountered_evidence_families, phase0_evidence_families, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/production_comparison_provenance.json`

Provenance of classifier outputs used for validation comparisons.

Created by: Explicit production-input identity and hash inventory.

Structure: `object: freeze_commit, production_inputs, schema_version, validation_outputs_freeze_sha256`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/rq1_u_correction_sensitivity.json`

Historical RQ1 denominator sensitivity before the generic U correction.

Created by: scripts/analyze/u_correction_sensitivity.py reconstructs old U states from all retained transitions and repeats the same weighted analysis.

Structure: `object: scope, old_rule_version, new_rule_version, rq1`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/scp_revision_diagnostics.json`

Frame filters, sample reconstruction, L states/reasons, paired attrition, token counts, and date-gap diagnostics.

Created by: scripts/prepare/revision_diagnostics.py from frozen inputs and separately collected official date metadata.

Structure: `object: scope, frame, hash_order_reproduces_frozen_200, l_states_by_distribution_stratum, acquisition_reasons_by_distribution_stratum, same_version_log_attrition, normalized_log_count, usable_log_count, incomplete_downloaded_log_count, historical_token_v1_0_by_primary_state, debian_endpoint_stamp_coverage, debian_endpoint_stamp_range_utc, date_limitations, additional_v1_1_negative_fixtures, fedora_worker_date_coverage, fedora_worker_date_range_utc, strict_pair_record_date_gap_fedora_minus_debian_days`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/study_chronology.json`

Historical workflow stages and warranted provenance wording.

Created by: Repository-based chronology distinguishing internal protocol, sampling freeze, generic corrections, primary analysis, and post-hoc trace.

Structure: `object: schema_version, events`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/token_v1_1_zero_success_check.json`

Added zero-success exclusions and their effect on retained token candidate sets.

Created by: scripts/validate/check_token_v1_1.py rechecks v1.0 tokens with the v1.1 exclusion; no change across 194 log decisions and three additional negatives rejected.

Structure: `object: scope, limitation, candidate_log_count, historical_positives, changed_log_count, additional_negatives, records`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u88_blind_input.json`

Frozen 88-case U validation inputs without production labels.

Created by: Deterministic label-blind validation-set preparation.

Structure: `object: protocol, records, schema_version, selection_manifest`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u88_production_comparison.json`

Production U comparisons for the initial 88-case exercise.

Created by: Join of frozen production and independent U outputs.

Structure: `object: confusion_matrix, records, schema_version, summary`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u88_validation_consensus.json`

Agreement, disagreement, and indeterminate states of the initial two U paths.

Created by: Comparison of native discovery and structured static inspection; indeterminate is not a negative reference.

Structure: `object: case_count, records, schema_version, status_counts`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u88_validator_a.json`

Bounded offline native-discovery U outputs.

Created by: First independently implemented automated validation path.

Structure: `object: case_count, certificates, schema_version, validator`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u88_validator_b.json`

Structured static-inspection U outputs.

Created by: Second independently implemented automated validation path.

Structure: `object: case_count, certificates, schema_version, validator`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_corrected_production_assessment.json`

Assessment of final U positives after generic corrections.

Created by: Combination of original positive certificates and supported counterexample certificates.

Structure: `object: claim_scope, confirmed_count, contradicted_count, counterexample_search, disposition, family_certification, final_positive_count, generic_defect, indeterminate_count, one_path_confirmed, provenance, records, rq1_changed, schema_version, two_path_confirmed`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_nonpositive_counterexample_search.json`

Supported-domain missed entrypoints among original nonpositive U observations.

Created by: Label-blind counterexample search followed by production comparison; no exhaustive absence claim.

Structure: `object: candidate_case_ids, case_count, confirmed_count, protocol_sha256, records, schema_version, status_counts, unresolved_candidate_count`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_positive_certificates.json`

Artifact-linked evidence for production-positive U eligibility claims.

Created by: Independent automated native/static checks with supporting file/target evidence.

Structure: `object: case_count, certificate_status_counts, certificates, family_certification, path_coverage, protocol_sha256, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_positive_output_freeze.json`

Frozen positive-validation output hashes and provenance.

Created by: Hash inventory of completed positive validation outputs.

Structure: `object: byte_identical, deterministic_run_1_inventory_sha256, deterministic_run_2_inventory_sha256, file_count, files, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_positive_validation_protocol.json`

State-specific positive-claim validation scope and rules.

Created by: Protocol for checking original positives and searching supported nonpositive cases.

Structure: `object: allowed_evidence, author_decision, counterexample_cases, decision_rules, environment, execution_constraints, forbidden_inputs, implementation, implementation_sha256, positive_cases, protocol, schema_version, selection, stop_rules, supported_families`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_positive_validation_summary.json`

Positive-certification and supported-miss summary counts.

Created by: Aggregation of retained certificates and counterexample search.

Structure: `object: counterexample_status_counts, generic_defect_assessment, positive, positive_status_counts, protocol_sha256, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/u_validation_manifest.json`

U validation case identities and input hashes.

Created by: Frozen manifest for automated U checks.

Structure: `object: author_decision, claim_boundary, state_specific_validation, status, symmetric_88_case_exercise`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/validation_implementation_freeze.json`

Independent-validation implementation identities and hashes.

Created by: Code inventory frozen for the automated validation exercise.

Structure: `object: environment, implementations, network_policy, protocol_commit, resource_policy, schema_version, u_contract_domain`. Full observed field types are in `DATA_SCHEMA.json`.

## `data/validation/validation_outputs_freeze.json`

Validation-output identities and hashes.

Created by: Content-hash inventory after completed validation.

Structure: `object: comparison_gate, deterministic_rerun, files, implementation_commits, protocol_commit, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `results/authoritative/scientific_results_posthoc_l_sensitivity.json`

Authoritative secondary generic-L sensitivity estimates.

Created by: Same analysis pipeline with the separate opt-in sensitivity labels.

Structure: `object: c2a, inference, retrievability, rq1, rq2, rq3`. Full observed field types are in `DATA_SCHEMA.json`.

## `results/authoritative/scientific_results_primary.json`

Authoritative primary RQ1/RQ2/RQ3 estimates, intervals, and archive subset results.

Created by: scripts/analyze/reproduce_results.py from frozen corrected-frame sample and primary U/P/L observations.

Structure: `object: c2a, inference, retrievability, rq1, rq2, rq3`. Full observed field types are in `DATA_SCHEMA.json`.

## `results/authoritative/typed_results.json`

Typed reported values with numerator, denominator, interval method, and weighting fields.

Created by: Typed reporting extraction from authoritative primary and sensitivity analysis.

Structure: `object: rows, schema_version`. Full observed field types are in `DATA_SCHEMA.json`.

## `results/release_manifest.json`

Release-file content hashes and distribution boundary.

Created by: Inventory of distributable package files; does not hash itself.

Structure: `object: files, redistribution, schema_version, source_repository`. Full observed field types are in `DATA_SCHEMA.json`.
