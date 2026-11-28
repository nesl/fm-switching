import json,hashlib,os
_D=os.path.dirname(os.path.abspath(__file__))
SRC='results/orchestration/live2/oracle/oracle_fair_table.json'
PATH=_D+'/oracle_fair_table.json'
if not os.path.exists(PATH):
    PATH=os.path.join(_D,'..','..','..',SRC)   # repo layout: experiments/analysis/oracle/ -> repo root
SHA256='f67be762b15762e44d0cb1bbad9924599f896cc07e3bb4b6cf0c91c4b408c562'
BLOB='947ad92a102581a9fcf0e30f7ac936832a15f511'
_KEYS={'A_RC_H':'recall|cloud|WITH_HISTORY','A_RC_N':'recall|cloud|WITHOUT_HISTORY','CR':'recall|device|NA','A_SC':'single_shot|cloud|COLD','A_SD':'single_shot|device|NA'}
PROV={'path':SRC,'origin_ref':'origin/main','git_blob':BLOB,'sha256':SHA256,'note':'D268 corrected conditioned FAIR table, commit d6b24cb9; FROZEN'}
_C=None
def load():
    global _C
    if _C is not None:return dict(_C)
    b=open(PATH,'rb').read()
    sha=hashlib.sha256(b).hexdigest()
    blob=hashlib.sha1(b'blob %d\0'%len(b)+b).hexdigest()
    if sha!=SHA256 or blob!=BLOB:
        raise SystemExit('FAIR TABLE MISMATCH: %s sha256 %s (want %s) blob %s (want %s). ABORT.'%(PATH,sha,SHA256,blob,BLOB))
    t=json.loads(b)['table']
    _C={k:t[v]['acc'] for k,v in _KEYS.items()}
    return dict(_C)
def oracle_total(robot_rows,ss_rows):
    c=load();return robot_rows*(c['A_RC_H']-c['CR'])+ss_rows*(c['A_SC']-c['A_SD'])
def banner(robot_rows,ss_rows,label=''):
    c=load()
    return ('FAIR CONSTANTS %s: '%label+' '.join('%s=%r'%(k,c[k]) for k in _KEYS)+'\n  source %s @%s blob %s sha256 %s (%s)\n  robot_rows=%d ss_rows(all assistive rows)=%d oracle_total=%d*(A_RC_H-CR)+%d*(A_SC-A_SD)=%.2f'
            %(PROV['path'],PROV['origin_ref'],BLOB,SHA256,PROV['note'],robot_rows,ss_rows,robot_rows,ss_rows,oracle_total(robot_rows,ss_rows)))
if __name__=='__main__':print(banner(0,0,'selfcheck'))
