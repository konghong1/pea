from playwright.sync_api import sync_playwright
import os, json, urllib.request, random, string, re

BASE = 'http://localhost:8088'
SHOTS = 'C:/workspace/pea/verify/shots'
os.makedirs(SHOTS, exist_ok=True)

def rand_email():
    return 'labelcheck_%s@pea.ai' % ''.join(random.choices(string.ascii_lowercase, k=6))

email = rand_email()
password = 'Password123'
data = json.dumps({'email': email, 'password': password}).encode()
urllib.request.urlopen(urllib.request.Request(BASE + '/auth/register', method='POST', data=data, headers={'Content-Type': 'application/json'}), timeout=15)
tok = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + '/auth/login', method='POST', data=data, headers={'Content-Type': 'application/json'}), timeout=15).read().decode())['token']
cv = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + '/canvases', method='POST', data=json.dumps({'title': 'labelcheck', 'type': 'personal'}).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % tok}), timeout=15).read().decode())
cid = cv['id']

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
    page = browser.new_context(viewport={'width': 1440, 'height': 900}).new_page()
    page.add_init_script("localStorage.setItem('__peaDevHooks','1');")
    page.add_init_script("localStorage.setItem('pea_token', '%s');" % tok)
    page.add_init_script("localStorage.setItem('pea_user', JSON.stringify({id:1,email:'%s'}));" % email)
    page.add_init_script("localStorage.setItem('pea_ui_route', JSON.stringify({active:'canvas',canvasId:%s}));" % cid)
    page.route(re.compile(r'.*?/users/me.*'), lambda r, req: r.fulfill(status=200, content_type='application/json', body=json.dumps({'id':1,'email':email,'displayName':'T','balance':0,'isAdmin':False,'planLevel':0,'effectivePlanLevel':0,'planExpiresAt':None})))
    page.route(re.compile(r'.*?/auth/refresh.*'), lambda r, req: r.fulfill(status=200, content_type='application/json', body=json.dumps({'token':tok})))
    page.route(re.compile(r'.*?/canvases(\?.*)?$'), lambda r, req: r.fulfill(status=200, content_type='application/json', body=json.dumps({'ok':True,'data':[]})))
    page.route(re.compile(r'.*?/canvases/\d+.*'), lambda r, req: r.fulfill(status=200, content_type='application/json', body=json.dumps({'id':cid,'title':'labelcheck','version':1,'graph_json':{'nodes':[],'edges':[]}})))
    page.route(re.compile(r'.*?/models/available.*'), lambda r, req: r.fulfill(status=200, content_type='application/json', body=json.dumps([{'id':'agnes','providerId':'agnes','type':'image','modelType':'image','name':'Agnes','displayName':'Agnes','unlocked':True,'basePrice':1}])))
    page.route(re.compile(r'.*?/models/estimate.*'), lambda r, req: r.fulfill(status=200, content_type='application/json', body=json.dumps({'estimate':1})))
    page.goto(BASE + '/', wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.wait_for_function('() => window.__canvas && window.__ui', timeout=15000)
    page.evaluate("""() => {
        const cs = window.__canvas.getState();
        cs.setCanvasMeta(%s, 1, 'labelcheck');
        cs.loadGraph([
            {id:'t1',type:'pea',position:{x:300,y:300},data:{kind:'text',label:'T1',html:'<p>T1</p>'}},
            {id:'t2',type:'pea',position:{x:700,y:300},data:{kind:'text',label:'T2',html:'<p>T2</p>'}},
            {id:'t3',type:'pea',position:{x:300,y:650},data:{kind:'text',label:'T3',html:'<p>T3</p>'}},
            {id:'t4',type:'pea',position:{x:700,y:650},data:{kind:'text',label:'T4',html:'<p>T4</p>'}},
        ], [], 1);
    }""" % cid)
    page.wait_for_timeout(1500)
    gid = page.evaluate("() => window.__canvas.getState().groupNodes(['t1','t2','t3','t4'])")
    page.wait_for_timeout(1000)
    page.evaluate("([g]) => window.__canvas.getState().setSelection([g])", [gid])
    page.wait_for_timeout(1000)
    label = page.evaluate("""() => {
        const el = document.querySelector('.pea-group-node-label');
        const node = document.querySelector('.pea-group-node');
        const rfNode = document.querySelector('.react-flow__node[data-id^="group_"]');
        return {
            label: el ? {
                text: el.textContent,
                rect: el.getBoundingClientRect().toJSON(),
                computed: {
                    color: window.getComputedStyle(el).color,
                    backgroundColor: window.getComputedStyle(el).backgroundColor,
                    position: window.getComputedStyle(el).position,
                    top: window.getComputedStyle(el).top,
                    left: window.getComputedStyle(el).left,
                    zIndex: window.getComputedStyle(el).zIndex,
                    opacity: window.getComputedStyle(el).opacity,
                    display: window.getComputedStyle(el).display,
                    visibility: window.getComputedStyle(el).visibility,
                }
            } : null,
            node: node ? {
                rect: node.getBoundingClientRect().toJSON(),
                classes: node.className,
                style: node.getAttribute('style'),
                position: window.getComputedStyle(node).position,
                overflow: window.getComputedStyle(node).overflow,
            } : null,
            rfNode: rfNode ? {
                rect: rfNode.getBoundingClientRect().toJSON(),
                classes: rfNode.className,
                position: window.getComputedStyle(rfNode).position,
                overflow: window.getComputedStyle(rfNode).overflow,
            } : null,
        };
    }""")
    print(json.dumps(label, indent=2, ensure_ascii=False))
    page.screenshot(path=os.path.join(SHOTS, 'live_label_check.png'))
    # 放大左上角区域，确认 label 可见
    grp = page.query_selector('.pea-group-node')
    if grp:
        bbox = grp.bounding_box()
        if bbox:
            page.screenshot(path=os.path.join(SHOTS, 'live_label_check_zoom.png'), clip={
                'x': bbox['x'] - 20, 'y': bbox['y'] - 40, 'width': 160, 'height': 100
            })
    browser.close()
