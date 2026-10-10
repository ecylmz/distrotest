#!/usr/bin/env python3
"""Render SCP revision figures from immutable primary evidence; no analysis refit."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/reproduced/figures'
SOURCES = ['results/authoritative/typed_results.json',
           'data/derived/automatic_upl_labels_primary.json']
ROWS = json.loads((ROOT / SOURCES[0]).read_text())['rows']
LABELS = json.loads((ROOT / SOURCES[1]).read_text())
COLORS = ['#0072B2', '#A54D00']
plt.rcParams.update({'font.size': 10, 'font.family': 'DejaVu Sans',
                     'pdf.fonttype': 42, 'ps.fonttype': 42,
                     'svg.fonttype': 'none', 'svg.hashsalt': 'distrotest-scp-major-revision', 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': 'white',
                     'axes.facecolor': 'white', 'savefig.facecolor': 'white'})
manifest = {'sources': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
            'software': {'matplotlib': matplotlib.__version__},
            'transformation': 'Counts and typed estimates only; percentages = 100 * point; no refit.',
            'figures': {}}

def save(fig, name, description, data):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    for fmt in ('pdf', 'svg', 'png'):
        metadata = {'Creator': 'Matplotlib', 'CreationDate': None, 'ModDate': None} if fmt == 'pdf' else ({'Date': None} if fmt == 'svg' else {})
        fig.savefig(OUT / f'{name}.{fmt}', dpi=600, metadata=metadata)
    manifest['figures'][name] = {'description': description, 'data': data,
                                  'width_inches': fig.get_figwidth(), 'height_inches': fig.get_figheight(),
                                  'png_dpi': 600, 'baseline': 0, 'color_redundancy': 'Labels and distinct markers or hatching'}
    plt.close(fig)

states = ['U_TEST_ENTRYPOINT_RESOLVED', 'U_TEST_ASSETS_ONLY', 'U_NO_TEST_CAPABILITY_RESOLVED', 'U_UNRESOLVED']
labels = ['Executable entrypoint', 'Test assets only', 'No supported capability resolved', 'Unresolved']
fig, ax = plt.subplots(figsize=(7.1, 3.25), layout='constrained')
y = np.arange(4)
data = {}
for i, distro in enumerate(('debian', 'fedora')):
    counts = Counter(r['state'] for r in LABELS['u'] if r['distribution'] == distro)
    assert sum(counts.values()) == 200
    values = [counts[s] for s in states]
    data[distro] = dict(zip(states, values))
    bars = ax.barh(y + (i-.5)*.34, np.array(values)/2, height=.31,
                   label=distro.title(), color=COLORS[i], hatch='' if i==0 else '///')
    ax.bar_label(bars, labels=[str(v) for v in values], padding=4, fontsize=10)
ax.set(yticks=y, yticklabels=labels, xlabel='Sample observations (%)', xlim=(0, 58))
ax.invert_yaxis(); ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.01), ncol=2, frameon=False); ax.set_axisbelow(True); ax.grid(axis='x', alpha=.18)
save(fig, 'scp_u_coverage', 'Four U states; unresolved cases account for nearly half of each sample. Raw n=200 per distribution.', data)

for panel, name, metrics, descriptions in [
 ('RQ1','scp_rq1',['record_retrievability','conditional_positive_evidence','overall_positive_evidence'],
  ['Exact record retrieved','Positive | U entrypoint + usable log','Positive | all U entrypoints']),
 ('RQ2','scp_rq2',['P_TEST_DECLARED','P_NO_CONVENTIONAL_TEST_DECLARATION_RESOLVED'],
  ['Declared intent','No conventional declaration'])]:
    fig, ax = plt.subplots(figsize=(7.1, 3.1 if panel=='RQ1' else 2.7), layout='constrained')
    data=[]
    for i, distro in enumerate(('debian','fedora')):
        for j, metric in enumerate(metrics):
            r=next(r for r in ROWS if r['panel']==panel and r['distribution']==distro and r['metric']==metric and r.get('analysis','revised_primary')=='revised_primary')
            p=100*r['point']; lo,hi=[100*v for v in r['interval']]; yy=j+(i-.5)*.25
            ax.errorbar(p, yy, xerr=[[p-lo],[hi-p]], fmt='o' if i==0 else 's', color=COLORS[i], capsize=3,
                        label=distro.title() if j==0 else None, markersize=6)
            ax.text(104, yy, f"{r['count']}/{r['denominator']}   {p:.1f}%", va='center', fontsize=9, color=COLORS[i])
            data.append(r)
    ax.set(yticks=np.arange(len(metrics)), yticklabels=descriptions, xlim=(-2,135),
           xticks=[0,25,50,75,100], xlabel='Design-weighted estimate (%) with 95% interval')
    ax.invert_yaxis();ax.set_axisbelow(True);ax.grid(axis='x',alpha=.18)
    ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.01), ncol=2, frameon=False); ax.spines['bottom'].set_bounds(0,100)
    save(fig,name,'Weighted estimates; labels are raw numerator/denominator. RQ2 Fedora zero uses unweighted Wilson uncertainty.',data)

# Derive all paired states from frozen labels and frozen sample; do not hardcode results.
sample=json.loads((ROOT/'data/manifests/sample_revision.json').read_text())
projects=sample.get('selected',sample.get('projects',[]))
# The corrected sample uses selected_projects.
if not projects: projects=sample.get('selected_projects',[])
lookup={(r['canonical_upstream'],r['distribution']):r['state'] for r in LABELS['l']}
paired=Counter()
usable={'L_POSITIVE_EXECUTION_EVIDENCE','L_NO_POSITIVE_EXECUTION_EVIDENCE','L_ZERO_TEST_EXECUTION_EVIDENCE'}
positive='L_POSITIVE_EXECUTION_EVIDENCE'
positive='L_EXECUTION_EVIDENCED'
usable={'L_EXECUTION_EVIDENCED','L_ZERO_TEST_EXECUTION_EVIDENCED','L_NO_POSITIVE_EXECUTION_EVIDENCE'}
for p in projects:
    if p.get('stratum') not in ('same_version','same_upstream_version','C2V'): continue
    cid=p['canonical_upstream']; a=lookup[(cid,'debian')]; b=lookup[(cid,'fedora')]
    if a not in usable or b not in usable: continue
    paired[('both' if a==positive and b==positive else 'Debian only' if a==positive else 'Fedora only' if b==positive else 'neither')]+=1
assert dict(paired)=={'both':17,'Debian only':4,'Fedora only':3,'neither':29}, (paired,list(sample),positive)
fig,ax=plt.subplots(figsize=(7.1,2.75),layout='constrained')
categories=['both','Debian only','Fedora only','neither']; counts=[paired[k] for k in categories]
bars=ax.barh(np.arange(4),counts,color=['#454545',*COLORS,'#9A9A9A'],hatch=['','', '///', '...'])
ax.bar_label(bars,labels=[f'{v}/53 ({100*v/53:.1f}%)' for v in counts],padding=5)
ax.set(yticks=np.arange(4),yticklabels=['Both positive','Debian only positive','Fedora only positive','Neither positive'],
       xlabel='Strict usable same-version pairs (count)',xlim=(0,38),xticks=[0,10,20,30])
ax.invert_yaxis();ax.set_axisbelow(True);ax.grid(axis='x',alpha=.18)
save(fig,'scp_rq3','Primary paired evidence labels; neither-positive does not establish non-execution.',dict(paired))
manifest['sources']['data/manifests/sample_revision.json']=hashlib.sha256((ROOT/'data/manifests/sample_revision.json').read_bytes()).hexdigest()
(OUT/'scp_figure_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
