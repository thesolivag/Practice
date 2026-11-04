"""Owner-only paper API. Import/create_app does not connect to external services."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from urllib.parse import parse_qsl

OWNER = '1410229777'


def validate_init_data(init_data, token, owner=OWNER, now=None, max_age=3600):
    if not init_data or not token or str(owner) != OWNER:
        raise ValueError('authentication unavailable')
    if len(init_data) > 16384:
        raise ValueError('invalid authentication')
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    if len({k for k, v in pairs}) != len(pairs):
        raise ValueError('duplicate authentication fields')
    values = dict(pairs)
    received = values.pop('hash', '')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(values.items()))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError('invalid authentication')
    try:
        auth_date = int(values['auth_date'])
        user = json.loads(values['user'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('invalid authentication') from None
    now = time.time() if now is None else now
    if auth_date <= 0 or not -30 <= now - auth_date <= max_age or str(user.get('id')) != OWNER:
        raise ValueError('authentication expired or owner mismatch')
    return user


def create_app(store=None, *, bot_token=None, local_api_key=None):
    from fastapi import FastAPI, Request, Depends, HTTPException
    from fastapi.responses import FileResponse
    from .paper_store import Store
    from . import settings
    # FastAPI evaluates annotations in module globals.
    globals()['Request'] = Request
    store = store if store is not None else Store(os.environ.get('BISHOP_PAPER_DB', ':memory:'))
    bot_token = bot_token if bot_token is not None else os.environ.get('BISHOP_TELEGRAM_BOT_TOKEN', '')
    app = FastAPI(title='Bishop Paper', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    static = Path(__file__).parent / 'web'

    def owner(request: Request):
        # Local key is accepted only when explicitly supplied to the factory and
        # the peer is loopback. Never use this mode in a remotely hosted service.
        provided = request.headers.get('X-Bishop-Owner-Key', '')
        if local_api_key and request.client and request.client.host in ('127.0.0.1', '::1') and hmac.compare_digest(provided, local_api_key):
            return {'id': int(OWNER)}
        try:
            return validate_init_data(request.headers.get('X-Telegram-Init-Data', ''), bot_token)
        except Exception:
            raise HTTPException(403, 'Owner authentication required') from None

    @app.middleware('http')
    async def bounds(request: Request, call_next):
        try:
            oversized = int(request.headers.get('content-length', '0')) > 65536
        except ValueError:
            oversized = True
        if len(request.url.query) > 8192 or oversized:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Request too large'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/healthz')
    def health():
        return {'ok': True}

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    @app.get('/app.js')
    def script():
        return FileResponse(static / 'app.js', media_type='application/javascript')

    @app.get('/api/me')
    def me(user=Depends(owner)):
        return {'id': user['id'], 'mode': 'paper'}

    @app.get('/api/settings/schema')
    def schema(user=Depends(owner)):
        return settings.schema_json()

    @app.get('/api/settings')
    def get_settings(user=Depends(owner)):
        return store.get_settings()

    @app.patch('/api/settings')
    async def change(request: Request, user=Depends(owner)):
        try:
            body = await request.json()
            return store.change_settings(body['changes'], body['revision'])
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid settings or revision conflict') from None

    collections = {'bias': 'bias', 'entries': 'entries', 'orders': 'orders', 'history': 'events', 'runs': 'paper_runs', 'jobs': 'job_requests'}

    @app.get('/api/status')
    def status(user=Depends(owner)):
        dispatch_configured = bool(os.environ.get('BISHOP_CRON_ENABLED') == 'true'
                                   and os.environ.get('BISHOP_CRON_SECRET') and os.environ.get('BISHOP_GH_DISPATCH_TOKEN'))
        return dict(mode='paper', delivery='ENABLED' if store.delivery_enabled else 'DISABLED', scheduled=False,
                    dispatch_configured=dispatch_configured,
                    capabilities={**settings.CAPABILITIES, 'telegram_delivery': store.delivery_enabled,
                                  'external_dispatch': dispatch_configured},
                    bias_scans=[{'instrument': row['instrument'], 'as_of': row['as_of']}
                                for row in store.list('bias_snapshots', 500)],
                    runs=store.list('paper_runs', 10))

    @app.get('/api/results/summary')
    def summary(user=Depends(owner)):
        return {'runs': [{'id': r['id'], 'as_of': r['result']['as_of'], 'summary': r['result'].get('summary'), 'coverage': r['result']['coverage']} for r in store.list('paper_runs', 100)]}

    @app.get('/api/bias-review')
    def bias_review(user=Depends(owner)):
        root = Path(__file__).resolve().parent.parent / 'reports' / 'bias_validation'
        inventory = json.loads((root / 'source_readiness.json').read_text())
        annotations = json.loads((root / 'source_annotations.json').read_text())
        diagnosis_path = root / 'diagnosis.json'
        diagnoses = json.loads(diagnosis_path.read_text())['cases'] if diagnosis_path.exists() else []
        inventory_path = root / 'snapshot_inventory.json'
        probes = json.loads(inventory_path.read_text())['examples'] if inventory_path.exists() else []
        from .v2.types import utc
        for row in annotations['examples']:
            row['snapshot_diagnostic'] = next((p for p in probes if p['case_id'] == row['case_id']), None)
            if row['snapshot_diagnostic'] is None:
                row['snapshot_diagnostic'] = next((d for d in diagnoses if d['instrument'] == row['pair']
                    and row.get('snapshot_time') and utc(d['as_of']) == utc(row['snapshot_time'])
                    and any(r.get('basis') == 'SAME_TIMEFRAME_STRUCTURE' for r in d['rows'])), None)
        return {'total': inventory['total'],
                'source_charts_reviewed': len(annotations['examples']),
                'source_labels_reviewed': sum(r.get('side') in ('BUY', 'SELL') and bool(r.get('bias_tf')) for r in annotations['examples']),
                'qualification': annotations['qualification'], 'items': annotations['examples']}

    @app.get('/api/source-chart/{case_id}')
    def source_chart(case_id: str, user=Depends(owner)):
        root = Path(__file__).resolve().parent.parent
        annotations = json.loads((root / 'reports/bias_validation/source_annotations.json').read_text())
        row = next((r for r in annotations['examples'] if r['case_id'] == case_id), None)
        if row is None:
            raise HTTPException(404, 'Unknown source example')
        evidence = row['evidence']
        if evidence.get('page'):
            path = static / 'source_charts' / f"page-{int(evidence['page']):02}.png"
        else:
            path = (root / evidence['path']).resolve()
            if not path.is_relative_to(root / 'knowledge-base/study/examples'):
                raise HTTPException(404)
        if path.suffix != '.png' or not path.is_file():
            raise HTTPException(404, 'Source chart unavailable')
        return FileResponse(path, media_type='image/png')

    @app.get('/api/bias/current')
    def current_bias(user=Depends(owner)):
        from .v2.types import utc
        grouped={}
        for item in store.list('bias_snapshots',500):
            grouped.setdefault(item['instrument'],[]).append(item)
        current=[]
        for instrument,items in sorted(grouped.items()):
            confirmed=[item for item in items if any(row.get('basis')=='CONFIRMED_STORIES'
                       for row in item.get('rows',()))]
            # Waiting/conflicted confirmed readings must not fall back to a
            # legacy naked structural direction. Preserve old rows as history.
            current.append(max(confirmed or items,key=lambda item:utc(item['as_of'])))
        return {'items':current}

    @app.post('/api/jobs')
    async def job(request: Request, user=Depends(owner)):
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('object required')
            if set(body) - {'kind', 'input_reference', 'manifest_reference', 'as_of', 'history_start', 'scan_start', 'costs', 'examples_reference', 'management_actions'}:
                raise ValueError('unknown fields')
            if not isinstance(body.get('input_reference'), str) or len(body['input_reference']) > 1024:
                raise ValueError('input reference required')
            from .v2.types import utc
            utc(body['as_of'])
            from .runner import validate_management_actions
            validate_management_actions(body.get('management_actions', []))
            if not isinstance(body.get('manifest_reference'), str) or not isinstance(body.get('costs'), dict):
                raise ValueError('manifest and costs required')
            if body.get('kind') == 'replay' and not isinstance(body.get('examples_reference'), str):
                raise ValueError('examples reference required')
            return store.request_job(request.headers.get('Idempotency-Key', ''), body)
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid offline job request') from None

    @app.get('/api/{collection}')
    def listing(collection: str, limit: int = 100, offset: int = 0, user=Depends(owner)):
        if collection not in collections:
            raise HTTPException(404)
        return {'items': store.list(collections[collection], limit, offset), 'offset': max(offset, 0), 'limit': min(max(limit, 1), 500)}

    @app.get('/api/{collection}/{record_id}')
    def detail(collection: str, record_id: str, user=Depends(owner)):
        if collection not in collections:
            raise HTTPException(404)
        with store.lock:
            row = store._get(collections[collection], record_id)
        if row is None:
            raise HTTPException(404)
        return row

    @app.post('/cron/tick')
    def cron(request: Request):
        secret = os.environ.get('BISHOP_CRON_SECRET', '')
        provided = request.headers.get('X-Bishop-Cron-Key', '')
        if os.environ.get('BISHOP_CRON_ENABLED') != 'true' or not secret or not hmac.compare_digest(secret, provided):
            raise HTTPException(403, 'Bishop cron authentication required')
        token = os.environ.get('BISHOP_GH_DISPATCH_TOKEN', '')
        if not token:
            raise HTTPException(503, 'Bishop dispatch is not configured')
        try:
            from .dispatch import dispatch_bias
            return dispatch_bias(token)
        except Exception:
            raise HTTPException(502, 'Bishop workflow dispatch failed') from None

    return app
