"""Export the browser replay as readable static PDF/PNG artifacts.

Requires Chromium, Playwright and PyMuPDF in the document-rendering environment.
Does not run detection, simulation, acquisition or external publication.
"""
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright


def main():
    folder = Path('reports/visual_replay')
    output = fitz.open()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                              args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1500, 'height': 1100}, device_scale_factor=1)
        page.set_content((folder / 'bishop_examples.html').read_text())
        page.add_style_tag(content='''nav,.controls,#plan,details,dialog{display:none!important}
            .source{max-height:660px}.note{font-size:13px}main{padding:20px}
            .card{margin:12px 0;padding:16px}.cols{grid-template-columns:0.8fr 1.5fr}
            label{display:none}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}''')
        for i, name in enumerate(('EURNZD', 'GBPUSD')):
            page.evaluate(f'showCase({i})')
            page.evaluate('''() => { for (const p of document.querySelectorAll('p.note')) {
                p.textContent=p.textContent.replace('Click to enlarge. ', '')
                    .replace('Hover over candles for observed OHLC.', ''); } }''')
            page.screenshot(path=str(folder / f'Bishop-{name}-replay.png'), full_page=True)
            pdf = page.pdf(width='1500px', height='2050px', print_background=True,
                           margin={k: '0' for k in ('top', 'bottom', 'left', 'right')})
            source = fitz.open(stream=pdf, filetype='pdf')
            output.insert_pdf(source)
        browser.close()
    assert len(output) == 2
    assert all('Bot' in page.get_text() for page in output)
    output.save(str(folder / 'Bishop-teacher-vs-bot.pdf'))
    print('Exported and verified two PDF pages and two PNG previews.')


if __name__ == '__main__':
    main()
