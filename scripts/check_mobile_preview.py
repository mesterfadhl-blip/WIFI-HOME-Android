from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':390,'height':844})
    errors=[];requests=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda request:requests.append(request.url))
    # Managed Chromium blocks file navigation. Check the standalone content
    # in an empty document instead, without relaxing that policy.
    page.set_content(Path('preview/WIFI-HOME-PREVIEW.html').read_text())
    page.get_by_role('heading',name='فواتير المبيعات',exact=True).wait_for()
    for route in ['customers','products','purchases','suppliers','returns','finance','settlements','banks','warehouses','reports','audit','users','new','new-purchase','new-transfer']:
        page.evaluate('(route)=>{location.hash=route}',route)
        page.wait_for_timeout(80)
        assert page.locator('h1').count()==1, route
    page.evaluate("location.hash='sales'");page.wait_for_timeout(100)
    page.locator('[data-open="1"]').click()
    page.get_by_role('heading',name='SI-000001',exact=True,level=1).wait_for()
    page.locator('a[href="/print/invoices/1"]').click()
    page.frame_locator('#preview-doc').get_by_role('heading',name='فاتورة مبيعات',exact=True).wait_for()
    page.locator('#close-doc').click()
    page.locator('nav a[href="#reports"]').click()
    page.get_by_role('heading',name='تقارير المبيعات والحسابات',exact=True).wait_for()
    assert not errors,errors
    assert not [u for u in requests if u.startswith(('http:','https:'))], requests
    print('Standalone content: mobile navigation, invoice and reports passed; zero network requests.')
    browser.close()
