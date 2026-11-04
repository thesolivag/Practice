"""Local authenticated UI preview from archived Actions results; no hosted/broker connection."""
import json
from pathlib import Path
from urllib.parse import urlparse
from fastapi.testclient import TestClient
from bishop.webapp import create_app
from bishop.paper_store import Store


def main():
    from playwright.sync_api import sync_playwright
    store = Store()
    root = Path('reports/bias_validation')
    out = root / 'previews'
    out.mkdir(exist_ok=True)
    for path in (root / 'current_results').glob('*-engine.json'):
        result = json.loads(path.read_text())
        store.persist_result(result, result['as_of'], namespace='preview-' + result['instrument']['symbol'])
    with TestClient(create_app(store, local_api_key='preview-local-only'), client=('127.0.0.1', 123)) as client, sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1100, 'height': 1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def handler(route):
            parsed = urlparse(route.request.url)
            if parsed.netloc != 'bishop.test':
                route.fulfill(status=200, body='', content_type='application/javascript')
                return
            response = client.get(parsed.path, headers={'X-Bishop-Owner-Key': 'preview-local-only'})
            route.fulfill(status=response.status_code, body=response.content,
                          content_type=response.headers.get('content-type', 'text/plain'))
        page.route('**/*', handler)
        page.goto('http://bishop.test/', wait_until='networkidle')
        page.get_by_text('EURNZD', exact=True).wait_for()
        page.screenshot(path=str(out / 'current-bias-desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(out / 'current-bias-mobile.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.get_by_role('button', name='Bias review', exact=True).click()
        page.get_by_text('40 source examples reviewed; 27 explicit bias directions.').wait_for()
        page.screenshot(path=str(out / 'review-mobile.png'))
        article = page.get_by_role('heading', name='EURNZD · Bearish · D', exact=True).first.locator('..')
        article.get_by_role('button', name='View original chart').click()
        article.locator('img').wait_for()
        page.wait_for_function('Array.from(document.images).some(x=>x.complete&&x.naturalWidth>0)')
        page.set_viewport_size({'width': 1100, 'height': 900})
        article.screenshot(path=str(out / 'source-chart-desktop.png'))
        assert not errors, errors
        browser.close()
    print('Archived results and source image render; no JS errors or mobile overflow. Local TestClient only.')


if __name__ == '__main__':
    main()
