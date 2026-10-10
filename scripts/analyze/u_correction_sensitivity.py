#!/usr/bin/env python3
"""Reproduce the pre-U-correction RQ1 view from retained state transitions."""
from pathlib import Path
import copy, json
from distrotest_lite.revision_analysis import analyze_revision
ROOT=Path(__file__).resolve().parents[2]
def read(p): return json.loads((ROOT/p).read_text())
labels=copy.deepcopy(read('data/derived/automatic_upl_labels_primary.json'))
trans=read('data/derived/u_label_transitions_v1.1.0_to_v1.2.0.json')
old={(r['canonical_upstream'],r['distribution']):r for r in trans['records']}
for r in labels['u']:
    o=old[r['canonical_upstream'],r['distribution']];r['state']=o['old_state'];r['family']=o['old_family']
labels['rule_versions']['u']=trans['old_rule_version']
result,_=analyze_revision(read('data/manifests/sample_revision.json'),labels,read('data/manifests/log_acquisition.json')['records'],read('data/manifests/c2a_primary_archive.json'))
out={'scope':'Historical RQ1 denominator sensitivity before generic U correction; primary results remain unchanged.',
     'old_rule_version':trans['old_rule_version'],'new_rule_version':trans['new_rule_version'],'rq1':result['rq1']}
(ROOT/'data/validation/rq1_u_correction_sensitivity.json').write_text(json.dumps(out,indent=2)+'\n')
print('Wrote historical U-denominator sensitivity')
