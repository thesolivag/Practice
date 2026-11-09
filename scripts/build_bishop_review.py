"""Package frozen research records; never reads live accounts or broker credentials."""
import argparse,csv,gzip,json
from pathlib import Path

def read(p):
    with gzip.open(p,'rt') as f:return json.load(f)
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.GzipFile(filename=str(p),mode='wb',mtime=0) as f:f.write(json.dumps(x,separators=(',',':')).encode())
def build(checkpoints,feeds,ledger,evidence,out):
    final={r['order_id']:r for r in csv.DictReader(open(ledger))}
    rich={x['row']['order']['setup_id']:x for x in read(evidence)}
    entries=[]
    for p in sorted(Path(checkpoints).glob('*/checkpoint.json.gz')):
        pair=p.parent.name; feed=read(Path(feeds)/(pair+'.json.gz')); tick=float(feed['instrument']['tick_size'])
        write(out/(pair+'.json.gz'),feed)
        groups={}
        for r in read(p)['book'].values():
            o=r['order']; mode=r['mode']; family=mode.rsplit('_',1)[0]+'_RR' if mode.endswith(('1R','2R','3R')) else mode
            key=(o['setup_id'],family)
            if key not in groups:
                sample=rich.get(o['setup_id']); flow=sample['flow_matches'][0] if sample and family=='recognition_RR' else None
                groups[key]={'id':o['id'].removesuffix('_r1').removesuffix('_r2').removesuffix('_r3')+'_'+family,'pair':pair,'strategy':family,'confirmation':{'confirmation_bo':'breakout','confirmation_standing_extreme':'4th man','engulf_av_retest':'engulfing'}.get(o['model'],o['model']),'tf':o['tf'],'side':o['side'],'decision':o['clock']['available_at'],'entry':float(o['entry_ticks'])*tick,'stop':float(o['stop_ticks'])*tick,'kind':o['kind'],'bias':r.get('bias'),'stop_proof':r.get('stop_proof'),'targets':[],'flow':flow,'highlight':bool(flow),'tick_size':tick,'cutoff':feed['bars'][-1]['available_at']}
            corrected=final.get(o['id'])
            if not corrected:raise ValueError('Missing corrected ledger row '+o['id'])
            groups[key]['targets'].append({'label':mode.rsplit('_',1)[-1] if family.endswith('RR') else 'Nearby','price':float(o['target_ticks'])*tick,'order_id':o['id'],'result':{'outcome':corrected['outcome'],'gross_R':corrected['gross_R'],'observed_at':corrected['close_observed_UTC'],'fill_start':corrected['fill_window_start'],'fill_end':corrected['fill_window_end']}})
        entries.extend(groups.values())
    for e in entries:e['targets'].sort(key=lambda x:x['label'])
    entries.sort(key=lambda x:(not x['highlight'],x['decision'],x['pair'],x['strategy']))
    write(out/'index.json.gz',{'source_run':'42371042901','correction_runs':['42499187752','42516446781'],'notice':'Frozen 2026 comparison, with minute-resolution corrections. This is the original capacity-limited cohort, not the newer capacity study. Gross results exclude trading costs. H4 sequence annotations are available for the three audited recognition examples only.','entries':entries})
    print('Packaged',len(entries),'setups across',len({e['pair'] for e in entries}),'markets;',sum(e['highlight'] for e in entries),'fully annotated examples')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoints',required=True);p.add_argument('--feeds',required=True);p.add_argument('--ledger',required=True);p.add_argument('--evidence',required=True);p.add_argument('--out',type=Path,default=Path('data/bishop_review'));a=p.parse_args();build(a.checkpoints,a.feeds,a.ledger,a.evidence,a.out)
