"""Serialize broker work across independent GitHub workflow groups.

A nonblocking personal-alert tick never displaces an hourly workflow in GitHub's
single pending slot. MySQL owns the cross-run lock; disconnect releases it.
"""
import argparse
import json
from contextlib import contextmanager

LOCK = 'slk_market_feed'


@contextmanager
def feed_lock(db, wait=0, name=LOCK):
    connection = db.connect()
    acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT GET_LOCK(%s,%s) AS ok', (name, wait))
            acquired = bool(cursor.fetchone()['ok'])
        yield acquired
    finally:
        if acquired:
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))
            finally:
                connection.close()
        else:
            connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('job',choices=['live','alerts','backfill'])
    args,remaining=parser.parse_known_args(argv)
    from . import db
    # Personal watches are deferred rather than competing with the hourly scanner.
    with feed_lock(db,0 if args.job=='alerts' else 240,name='slk_personal_feed' if args.job=='alerts' else LOCK) as acquired:
        if not acquired:
            print(json.dumps({'skipped':'Another broker job owns the feed; the next check will catch up.'}),flush=True)
            return 0
        if args.job=='live':
            from . import live
            return live.main(remaining)
        if args.job=='backfill':
            from . import store
            return store.main(remaining)
        from . import user_alerts
        print(json.dumps(user_alerts.tick(),default=str),flush=True)
        return 0


if __name__=='__main__':
    raise SystemExit(main())
