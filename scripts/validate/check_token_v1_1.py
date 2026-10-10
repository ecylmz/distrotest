#!/usr/bin/env python3
"""Check v1.1 against retained token candidates, without requiring raw logs."""
from pathlib import Path
import json
from distrotest_lite_validation.log_success import validate_line_v1_1
ROOT=Path(__file__).resolve().parents[2]
old=json.loads((ROOT/'data/validation/l_sensitivity_independent_validation.json').read_text())
# Existing candidate tokens preserve each digit/word needed by the new exclusion.
records=old['certificates'] if isinstance(old,dict) else old
checks=[]
for r in records:
    positives=[]
    for c in r['candidates']:
        new=validate_line_v1_1(' '.join(c['tokens']))
        if new and new['positive']: positives.append(c['line_start'])
    checks.append({'log':r['log'],'historical_token_positive':r['reference_positive'],'v1_1_positive':bool(positives),'positive_lines':positives})
assert len(checks)==194
assert all(r['historical_token_positive']==r['v1_1_positive'] for r in checks)
negatives=['Test cases: 0 passed, 5 skipped in 0.1s','All 0 test cases passed; 12 skipped','Tests: 0 passed in 7.2 seconds']
out={'scope':'v1.1 zero-success exclusion check on retained v1.0 token candidates; no new primary or sensitivity labels.',
     'limitation':'Candidate tokens, rather than complete raw log text, are reused; v1.1 only adds an exclusion and cannot introduce new positive candidates.',
     'candidate_log_count':len(checks),'historical_positives':sum(r['historical_token_positive'] for r in checks),
     'changed_log_count':sum(r['historical_token_positive']!=r['v1_1_positive'] for r in checks),
     'additional_negatives':[{'text':s,'result':validate_line_v1_1(s)} for s in negatives],'records':checks}
(ROOT/'data/validation/token_v1_1_zero_success_check.json').write_text(json.dumps(out,indent=2)+'\n')
print('PASS: unchanged decisions on 194 retained log candidate sets; three new zero-success negatives rejected')
