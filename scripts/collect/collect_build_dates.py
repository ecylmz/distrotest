#!/usr/bin/env python3
"""Collect date metadata for frozen official record identities, without replacing logs."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor
import xmlrpc.client
import socket
import json
ROOT=Path(__file__).resolve().parents[2]
socket.setdefaulttimeout(25)
logs=json.loads((ROOT/'data/manifests/log_acquisition.json').read_text())['records']

def collect(r):
    item={'canonical_upstream':r['canonical_upstream'],'distribution':r['distribution'],
          'official_identifier':r.get('official_identifier'),'raw_sha256':r.get('raw_sha256')}
    if r['distribution']=='debian':
        stamp=parse_qs(urlparse(r.get('official_identifier','')).query).get('stamp')
        if stamp: item.update(date_source='buildd endpoint stamp',date_utc=datetime.fromtimestamp(int(stamp[0]),timezone.utc).isoformat())
        return item
    try:
        client=xmlrpc.client.ServerProxy('https://koji.fedoraproject.org/kojihub')
        b=client.getBuild(r['build_id']);t=client.getTaskInfo(r['task_id'])
        if b['nvr']!=r['nvr']: raise ValueError('Frozen NVR mismatch')
        item.update(date_source='Koji selected worker task create_ts',date_utc=datetime.fromtimestamp(t['create_ts'],timezone.utc).isoformat(),
                    build_id=b['id'],nvr=b['nvr'],worker_task_id=t['id'],worker_arch=t.get('arch'),
                    build_start_time=b.get('start_time'),build_completion_time=b.get('completion_time'))
    except Exception as e: item['metadata_error']=type(e).__name__+': '+str(e)[:160]
    return item
retained=[r for r in logs if r.get('normalized_path')]
with ThreadPoolExecutor(max_workers=4) as ex: records=list(ex.map(collect,retained))
out={'collected_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Date metadata only for the 194 retained normalized records; frozen versions, logs, and labels remain unchanged.',
     'interpretation':'Debian endpoint stamps and Fedora selected-worker task creation times are record-date proxies. They do not certify identical toolchains or build timing.',
     'records':records}
p=ROOT/'data/manifests/build_dates_scp_revision.json';p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'records':len(records),'date_coverage':sum('date_utc' in r for r in records),'errors':sum('metadata_error' in r for r in records)}))
