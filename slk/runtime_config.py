"""Private broker application credentials for the server-side minute checker.

The existing database already holds broker OAuth tokens. These application/account
server-only keys are never part of the public settings schema or extension.
"""
import os
from . import tenancy

KEYS=('ctrader_client_id','ctrader_client_secret','ctrader_account_id','ctrader_environment')


def _environment():
    return tuple(os.environ.get(name,'').strip() for name in ('CTRADER_CLIENT_ID','CTRADER_CLIENT_SECRET'))


def load(settings=None):
    """Read one coherent environment or global DB application/account configuration."""
    pair=_environment()
    if all(pair):
        values=dict(zip(KEYS,(*pair,os.environ.get('CTRADER_ACCOUNT_ID'),os.environ.get('CTRADER_ENV') or 'demo')))
    else:
        if settings is None:
            if not os.environ.get('DATABASE_URL'):return {}
            from . import db
        else:
            from ctrader.tokens import DbSettings
            if not isinstance(settings,DbSettings):return {}
            db=settings.db
        with tenancy.scope(None):
            conn=db.connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT k,v FROM settings WHERE k IN (%s,%s,%s,%s)',KEYS)
                    values={row['k']:row['v'] for row in cursor.fetchall()}
            finally:conn.close()
    if not all(values.get(key) for key in KEYS[:2]):return {}
    environment=values.get(KEYS[3]) or 'demo'
    if environment not in ('demo','live'):raise RuntimeError('Invalid private broker environment')
    return {'client_id':values[KEYS[0]],'client_secret':values[KEYS[1]],
            'account_id':values.get(KEYS[2]),'environment':environment}


def credentials(settings=None):
    config=load(settings)
    return config.get('client_id'),config.get('client_secret')


def sync(db=None):
    """Called only on a trusted Actions runner with the existing repository secrets."""
    pair=_environment()
    if not all(pair):return {'synced':False,'reason':'complete broker application credentials are not configured'}
    if db is None:
        from . import db
    from ctrader.tokens import DbSettings,_oauth_lock
    with _oauth_lock(DbSettings(db)) as conn:
        try:
            conn.begin()
            with conn.cursor() as cursor:
                cursor.executemany('INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)',list(zip(KEYS,(*pair,os.environ.get('CTRADER_ACCOUNT_ID'),os.environ.get('CTRADER_ENV') or 'demo'))))
                bootstrap={key:os.environ.get(name,'') for key,name in
                           (('ctrader_access_token','CTRADER_ACCESS_TOKEN'),('ctrader_refresh_token','CTRADER_REFRESH_TOKEN'))}
                cursor.execute('SELECT k,v FROM settings WHERE k IN (%s,%s)',tuple(bootstrap))
                stored={row['k']:row['v'] for row in cursor.fetchall()}
                missing=[key for key in bootstrap if not stored.get(key)]
                seeds=[]
                if missing and all(bootstrap.values()):
                    # A partial stored pair can only be completed from the same
                    # bootstrap pair; never combine an old token with a rotated one.
                    if any(stored.get(key) and stored[key]!=bootstrap[key] for key in bootstrap):
                        raise RuntimeError('Stored broker token pair is incomplete; reauthorize it before enabling server checks')
                    seeds=[(key,bootstrap[key]) for key in missing]
                if seeds:
                    cursor.executemany("INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=IF(v IS NULL OR v='',VALUES(v),v)",seeds)
            conn.commit()
        except Exception:
            conn.rollback();raise
    return {'synced':True}


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser();parser.add_argument('--sync',action='store_true');args=parser.parse_args()
    if args.sync:print(json.dumps(sync()))
