"""Package existing saved reference evidence, without replay or future outcomes."""
import argparse,gzip,json
from pathlib import Path
from slk.bishop_entry_reference import metadata

def build(checkpoints,archive,out):
    refs={}
    for p in sorted(Path(checkpoints).glob('*/checkpoint.json.gz')):
        pair=p.parent.name
        with gzip.open(Path(archive)/(pair+'.json.gz'),'rt') as f:tick=float(json.load(f)['instrument']['tick_size'])
        with gzip.open(p,'rt') as f:book=json.load(f)['book']
        refs.update(metadata(book,tick))
    raw=json.dumps({'source_run':'42371042901','references':refs},separators=(',',':')).encode()
    Path(out).write_bytes(gzip.compress(raw,mtime=0))
    print('Packaged',len(refs),'entry references')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoints',required=True);p.add_argument('--archive',default='data/bishop_review');p.add_argument('--out',default='data/bishop_review/entry_references.json.gz');a=p.parse_args();build(a.checkpoints,a.archive,a.out)
