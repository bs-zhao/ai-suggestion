#!/usr/bin/env python3
"""Convert the proprietary questionnaire export to analysis-only CSVs.

READ THE CONSENT NOTICE BEFORE SHARING. The questionnaire discloses research-only
storage of responses. Do not publish the resulting subject-level CSVs publicly.

No third-party Excel package required: ZIP and XML parsing use stdlib only.
"""
from __future__ import annotations
import argparse
import csv
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RECS=['B','A','A','A','A','B','A','B','B','B','B','A']
CONF={'非常不确定':1,'比较不确定':2,'一般':3,'比较确定':4,'非常确定':5}
LIKERT={'非常不同意':1,'比较不同意':2,'既不同意也不反对':3,'比较同意':4,'非常同意':5}


def col_idx(ref):
    letters=re.match(r'^[A-Z]+',ref).group(0)
    n=0
    for letter in letters:n=26*n+ord(letter)-64
    return n-1


def load_xlsx(path):
    with ZipFile(path) as f:
        strings=[]
        if 'xl/sharedStrings.xml' in f.namelist():
            root=ET.fromstring(f.read('xl/sharedStrings.xml'))
            strings=[''.join(t.text or '' for t in element.findall('.//x:t',NS)) for element in root.findall('x:si',NS)]
        root=ET.fromstring(f.read('xl/worksheets/sheet1.xml'))
        raw=[]
        for row in root.findall('.//x:sheetData/x:row',NS):
            cells={}
            for cell in row.findall('x:c',NS):
                typ=cell.attrib.get('t','')
                v=cell.find('x:v',NS)
                if typ=='inlineStr':
                    value=''.join(t.text or '' for t in cell.findall('.//x:is//x:t',NS))
                elif v is None:value=''
                elif typ=='s':value=strings[int(v.text)]
                else:value=v.text or ''
                cells[col_idx(cell.attrib['r'])]=value
            raw.append([cells.get(i,'') for i in range(142)])
        return raw


def write(path,records):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as fh:
        writer=csv.DictWriter(fh,fieldnames=list(records[0].keys()))
        writer.writeheader();writer.writerows(records)


def combine_original_exports(sources):
    """Combine untouched Excel exports, deduplicated by original response ID.

    data1.xlsx (30 respondents) is fully contained in data2.xlsx (60). We
    process the later file first so the original 60-person row order remains
    unchanged. Conflicting duplicate records are a hard error, never guessed.
    """
    sources=[Path(x) for x in sources]
    if not sources:
        raise ValueError('No original Excel exports supplied.')
    original_by_id={}
    reference_headers=None
    source_counts=[]
    duplicates=0
    # Most recent export last in command-line inputs; give it row-order priority.
    for source in reversed(sources):
        if not source.is_file():
            raise FileNotFoundError(f'Missing required original Excel export: {source}')
        rows=load_xlsx(source)
        if len(rows)<3:
            raise ValueError(f'Excel export contains no responses: {source}')
        headers=rows[:2]
        if reference_headers is None:
            reference_headers=headers
        elif headers!=reference_headers:
            raise ValueError(f'Original Excel question headers differ: {source}')
        source_counts.append((source.name,len(rows)-2))
        for row in rows[2:]:
            rid=str(row[0]).strip()
            if not rid:
                raise ValueError(f'Missing original response ID in {source}')
            if rid in original_by_id:
                if row!=original_by_id[rid]:
                    raise ValueError(f'Conflicting responses for original ID {rid!r} in {source}')
                duplicates+=1
            else:
                original_by_id[rid]=row
    body=list(original_by_id.values())
    if len(body)!=60:
        raise ValueError(f'Expected 60 distinct respondents after deduplication, got {len(body)}; source files: {source_counts}')
    return body,source_counts,duplicates


def convert(sources, target):
    if isinstance(sources, (str,Path)):
        sources=[Path(sources)]
    body,source_counts,duplicates=combine_original_exports(sources)
    participants=[]; trials=[]
    for i,r in enumerate(body,1):
        cond=r[17]
        if cond not in ('条件1','条件2'):
            raise ValueError(f'Unknown randomized assignment on participant {i}: {cond!r}')
        src='AI_label' if cond=='条件1' else 'Unlabeled'
        demo=21 if src=='AI_label' else 83
        survey=73 if src=='AI_label' else 135
        start=25 if src=='AI_label' else 87
        sid=f'S{i:03d}'
        p={'participant_id':sid,'source':src,
           'age_range':r[demo], 'country':r[demo+1],
           'language':r[demo+2], 'ai_frequency':r[demo+3],
           'duration_seconds':r[4]}
        for q in range(4):
            p[f'P{q+1}']=LIKERT.get(str(r[survey+q]).strip(),'')
            if p[f'P{q+1}']=='':raise ValueError(f'Missing P{q+1} for {sid}')
        p['source_recall']=r[survey+4]
        participants.append(p)
        for j in range(12):
            pair=[r[start+4*j],r[start+4*j+2]]
            choices=[]
            for answer in pair:
                hit=re.match(r'^\s*([AB])\s*[.．、:]?',str(answer))
                if hit is None:raise ValueError(f'Unexpected binary response: {sid}, E{j+1:02d}, {answer!r}')
                choices.append(hit.group(1))
            cf=[CONF.get(str(r[start+4*j+k]).strip()) for k in (1,3)]
            if any(v is None for v in cf):raise ValueError(f'Missing confidence: {sid}, E{j+1:02d}')
            agrees=choices[0]==RECS[j]
            changed=choices[0]!=choices[1]
            adopt=not agrees and choices[1]==RECS[j]
            trials.append({'participant_id':sid,'source':src,'scenario':f'E{j+1:02d}',
                           'recommendation':RECS[j],'initial_choice':choices[0],
                           'final_choice':choices[1], 'initial_confidence':cf[0],
                           'final_confidence':cf[1], 'confidence_change':cf[1]-cf[0],
                           'agrees_initially':int(agrees), 'changed_choice':int(changed),
                           'adopted_conflicting_advice':int(adopt)})
    assert Counter(p['source'] for p in participants)=={'AI_label':30,'Unlabeled':30}
    assert len(trials)==720
    write(target/'participants.csv',participants);write(target/'trials.csv',trials)
    print('Read',len(participants),'unique respondents and',len(trials),'trials from',source_counts,'; exact duplicate rows:',duplicates,'; saved to',target)
    print('No platform IDs, IPs, timestamps, coordinates, city, free text, or email are exported.')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',type=Path,nargs='+',required=True,help='Original raw exports (e.g. data/data1.xlsx data/data2.xlsx), with later exports last')
    ap.add_argument('--output-dir',type=Path,default=Path('data_private'))
    args=ap.parse_args()
    convert(args.input,args.output_dir)

if __name__=='__main__':main()
