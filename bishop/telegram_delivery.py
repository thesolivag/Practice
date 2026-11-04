"""Explicit Bishop-only Telegram outbox worker; never automatically retries uncertain sends."""
import os
import uuid
import time
from datetime import datetime, timezone


def deliver_pending(store, *, token, chat_id, post=None, limit=50):
    if not token or not chat_id:
        raise ValueError('Bishop Telegram token and destination are required')
    if not store.delivery_enabled:
        raise ValueError('Delivery is not enabled for this store')
    if post is None:
        import requests
        post = requests.post
    counts = dict(sent=0, failed=0, uncertain=0, deferred=0)
    for row in store.pending_alerts(limit):
        if row.get('status') != 'PENDING':
            continue
        claim = uuid.uuid4().hex
        with store.transaction():
            current = store._get('outbox', row['id'], lock=True)
            if current is None or current['status'] != 'PENDING' or current.get('next_attempt_at', 0) > time.time():
                continue
            current.update(status='SENDING', claim=claim,
                           attempted_at=datetime.now(timezone.utc).isoformat())
            store._put('outbox', row['id'], current)
        # Network timeouts may occur after Telegram accepted a message. Such rows
        # remain uncertain, never automatically resent by the next workflow.
        status, message_id, next_attempt = 'UNKNOWN', None, None
        try:
            response = post('https://api.telegram.org/bot' + token + '/sendMessage',
                            json={'chat_id': chat_id, 'text': row['text'],
                                  'disable_web_page_preview': True}, timeout=20)
            payload = response.json()
            if response.status_code == 200 and payload.get('ok') is True:
                status, message_id = 'SENT', payload.get('result', {}).get('message_id')
            elif isinstance(payload, dict) and payload.get('ok') is False:
                delay = payload.get('parameters', {}).get('retry_after')
                if response.status_code == 429 and type(delay) is int and delay > 0:
                    status, next_attempt = 'PENDING', time.time() + min(delay, 86400)
                else:
                    status = 'FAILED'
        except Exception:
            pass  # Never log URLs, remote descriptions, tokens or response bodies.
        with store.transaction():
            current = store._get('outbox', row['id'], lock=True)
            if current and current.get('claim') == claim and current['status'] == 'SENDING':
                current.update(status=status, message_id=message_id)
                if next_attempt is not None:
                    current['next_attempt_at'] = next_attempt
                store._put('outbox', row['id'], current)
        counts[{'SENT': 'sent', 'FAILED': 'failed', 'UNKNOWN': 'uncertain', 'PENDING': 'deferred'}[status]] += 1
    return counts


def main():
    import json
    from .runtime import application_store
    if os.environ.get('BISHOP_TELEGRAM_DELIVERY_ENABLED') != 'true':
        raise RuntimeError('Bishop Telegram delivery is disabled')
    result = deliver_pending(application_store(), token=os.environ.get('BISHOP_TELEGRAM_BOT_TOKEN', ''),
                             chat_id=os.environ.get('BISHOP_TELEGRAM_CHAT_ID', ''))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
