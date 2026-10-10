#!/usr/bin/env python3
"""Summarize frozen selection, log attrition, and narrow checker diagnostics."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import hashlib
import json
from statistics import median
from distrotest_lite.repositories import canonical_url, upstream_version
from distrotest_lite_validation.log_success import validate_line_v1_1
ROOT=Path(__file__).resolve().parents[2]

def read(p): return json.loads((ROOT/p).read_text())
sample=read('data/manifests/sample_revision.json'); labels=read('data/derived/automatic_upl_labels_primary.json')
logs=read('data/manifests/log_acquisition.json')['records']
projects={r['canonical_upstream']:r for r in sample['projects']}
frame={}; grouped={}
for d in ('debian','fedora'):
    source=read(f'data/manifests/source_indices/{d}_sources.json'); rows=source['records']; keys=defaultdict(list)
    for r in rows:
        cid,_=canonical_url(r.get('homepage',''))
        if cid: keys[cid].append(r)
    frame[d]={'source_records':len(rows),'keyed_records':sum(len(v) for v in keys.values()),'distinct_keys':len(keys),
              'unkeyed_records':len(rows)-sum(len(v) for v in keys.values()), 'snapshot_created_at':source['created_at']}
    grouped[d]=keys
shared=set(grouped['debian'])&set(grouped['fedora'])
resolved=[cid for cid in shared if len(grouped['debian'][cid])==len(grouped['fedora'][cid])==1]
frame.update(shared_keys=len(shared),ambiguous_shared_keys=len(shared)-len(resolved),resolved_projects=len(resolved))
ranked={}
for cid in resolved:
    dv=upstream_version('debian',grouped['debian'][cid][0]);fv=upstream_version('fedora',grouped['fedora'][cid][0]); st='C2V' if dv==fv and dv is not None else 'NON_C2V'
    ranked.setdefault(st,[]).append(cid)
selected=set()
for st,n in [('C2V',170),('NON_C2V',30)]:
    selected.update(sorted(ranked[st],key=lambda cid:(hashlib.sha256((sample['namespace']+'\0'+cid).encode()).hexdigest(),cid))[:n])
assert selected==set(projects)
L=defaultdict(Counter); reasons=defaultdict(Counter); lookup={}
for r in labels['l']:
    cid=r['canonical_upstream'];d=r['distribution'];st=projects[cid]['stratum'];lookup[cid,d]=r['state']
    L[d,st][r['state']]+=1
for r in logs:
    reasons[r['distribution'],projects[r['canonical_upstream']]['stratum']][r.get('reason') or r['state']]+=1
unresolved={'L_LOG_UNAVAILABLE','L_LOG_INCOMPLETE_OR_UNPARSABLE'}
pair=Counter()
for cid,p in projects.items():
    if p['stratum']!='C2V': continue
    du=lookup[cid,'debian'] not in unresolved;fu=lookup[cid,'fedora'] not in unresolved
    pair['both_usable' if du and fu else 'debian_only_usable' if du else 'fedora_only_usable' if fu else 'neither_usable']+=1
Ddates=[]
for r in logs:
    if r['distribution']=='debian' and r.get('official_identifier','').startswith('http'):
        stamp=parse_qs(urlparse(r['official_identifier']).query).get('stamp')
        if stamp: Ddates.append(datetime.fromtimestamp(int(stamp[0]),timezone.utc).isoformat())
checker=read('data/validation/l_sensitivity_production_vs_independent.json')
conf=Counter((r['primary_state'],r['independent_reference_positive']) for r in checker['records'])
out={'scope':'Descriptive frozen-input diagnostics; no primary outcomes changed.',
     'frame':frame,'hash_order_reproduces_frozen_200':True,
     'l_states_by_distribution_stratum':[{'distribution':d,'stratum':st,'counts':dict(c)} for (d,st),c in sorted(L.items())],
     'acquisition_reasons_by_distribution_stratum':[{'distribution':d,'stratum':st,'counts':dict(c)} for (d,st),c in sorted(reasons.items())],
     'same_version_log_attrition':dict(pair),
     'normalized_log_count':len(checker['records']), 'usable_log_count':sum(r['state']=='AVAILABLE' for r in logs),
     'incomplete_downloaded_log_count':sum(r['state']=='L_LOG_INCOMPLETE_OR_UNPARSABLE' for r in logs),
     'historical_token_v1_0_by_primary_state':[{'primary_state':a,'token_positive':b,'count':n} for (a,b),n in sorted(conf.items())],
     'debian_endpoint_stamp_coverage':len(Ddates),'debian_endpoint_stamp_range_utc':[min(Ddates),max(Ddates)],
     'date_limitations':'Endpoint stamps describe selected Debian records. Fedora build dates are not retained in these frozen manifests; paired temporal gaps cannot be inferred from acquisition timestamps.',
     'additional_v1_1_negative_fixtures':{s:validate_line_v1_1(s) for s in ['Test cases: 0 passed, 5 skipped in 0.1s','All 0 test cases passed; 12 skipped','Tests: 0 passed in 7.2 seconds']}}
dates=read('data/manifests/build_dates_scp_revision.json')
dmap={(r['canonical_upstream'],r['distribution']):datetime.fromisoformat(r['date_utc']) for r in dates['records'] if r.get('date_utc')}
gaps=[(dmap[cid,'fedora']-dmap[cid,'debian']).total_seconds()/86400 for cid,p in projects.items() if p['stratum']=='C2V' and lookup[cid,'debian'] not in unresolved and lookup[cid,'fedora'] not in unresolved and (cid,'debian') in dmap and (cid,'fedora') in dmap]
fdates=[r['date_utc'] for r in dates['records'] if r['distribution']=='fedora' and r.get('date_utc')]
out['fedora_worker_date_coverage']=len(fdates)
out['fedora_worker_date_range_utc']=[min(fdates),max(fdates)]
out['strict_pair_record_date_gap_fedora_minus_debian_days']={'n':len(gaps),'minimum':min(gaps),'median':median(gaps),'maximum':max(gaps)}
out['date_limitations']=dates['interpretation']
OUT=ROOT/'data/validation/scp_revision_diagnostics.json';OUT.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
