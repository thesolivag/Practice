"""Hosted paper application using only Bishop-owned application credentials."""
import os


def application_store():
    from .paper_store import Store
    url = os.environ.get('BISHOP_DATABASE_URL', '').strip()
    if not url:
        raise RuntimeError('BISHOP_DATABASE_URL is required; shared DATABASE_URL is not an application fallback')
    return Store(mysql_url=url,
                 mysql_password=os.environ.get('BISHOP_DATABASE_PASSWORD', ''),
                 mysql_ca=os.environ.get('BISHOP_DATABASE_CA', ''), migrate=True,
                 delivery_enabled=os.environ.get('BISHOP_TELEGRAM_DELIVERY_ENABLED') == 'true')


def create_hosted_app():
    from .webapp import create_app
    token = os.environ.get('BISHOP_TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('BISHOP_TELEGRAM_BOT_TOKEN is required')
    return create_app(store=application_store(), bot_token=token)
