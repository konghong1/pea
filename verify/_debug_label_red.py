from playwright.sync_api import sync_playwright
import os, json, urllib.request, random, string, re

BASE='http://localhost:8088'
SHOTS='C:/workspace/pea/verify/shots'
os.makedirs(SHOTS, exist_ok=True)

email='debug_%s@pea.ai'%''.join(random.choices(string.ascii_lowercase,k=6))
pw='Password123'
data=json.dumps({'email':email,'password':pw}).encode()
urllib.request.urlopen(urllib.request.Request(BASE+'/auth/register',method='POST',data=data,headers={'Content-Type':'application/json'}),timeout=15)
tok=json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/auth/login',method='POST',data=data,headers={'Content-Type':'application/json'}),timeout=15).read().decode())['token']
cv=json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/canvases',method='POST',data=json.dumps({'title':'debug','type':'personal'}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer %s'%tok}),timeout=15).read().decode())
cid=cv['id']

with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
    page=b.new_context(viewport={'width':1440,'height':900}).new_page()
    page.add_init_script("localStorage.setItem('__peaDevHooks','1');")
    page.add_init_script("localStorage.setItem('pea_token','%s');"%tok)
    page.add_init_script("localStorage.setItem('pea_user',JSON.stringify({id:1,email:'%s'}));"%email)
    page.add_init_script("localStorage.setItem('pea_ui_route',JSON.stringify({active:'canvas',canvasId:%s}));"%cid)
    page.route(re.compile(r'.*?/users/me.*'),lambda r,req:r.fulfill(status=200,content_type='application/json',body=json.dumps({'id':1,'email':email,'displayName':'T','balance':0,'isAdmin':False,'planLevel':0,'effectivePlanLevel':0,'planExpiresAt':None})))
    page.route(re.compile(r'.*?/auth/refresh.*'),lambda r,req:r.fulfill(status=200,content_type='application/json',body=json.dumps({'token':tok})))
    page.route(re.compile(r'.*?/canvases(\?.*)?$'),lambda r,req:r.fulfill(status=200,content_type='application/json',body=json.dumps({'ok':True,'data':[]})))
    page.route(re.compile(r'.*?/canvases/\d+.*'),lambda r,req:r.fulfill(status=200,content_type='application/json',body=json.dumps({'id':cid,'title':'debug','version':1,'graph_json':{'nodes':[],'edges':[]}})))
    page.route(re.compile(r'.*?/models/available.*'),lambda r,req:r.fulfill(status=200,content_type='application/json',body=json.dumps([{'id':'agnes','providerId':'agnes','type':'image','modelType':'image','name':'Agnes','displayName':'Agnes','unlocked':True,'basePrice':1}])))
    page.goto(BASE+'/',wait_until='domcontentloaded')
    page.wait_for_timeout(2500)
    page.wait_for_function('()=>window.__canvas&&window.__ui',timeout=15000)
    page.evaluate("""([cid])=>{
        const cs=window.__canvas.getState();
        cs.setCanvasMeta(cid,1,'debug');
        cs.loadGraph([
            {id:'t1',type:'pea',position:{x:300,y:300},data:{kind:'text',label:'T1',html:'<p>T1</p>'}},
            {id:'t2',type:'pea',position:{x:700,y:300},data:{kind:'text',label:'T2',html:'<p>T2</p>'}},
        ],[],1);
    }""",[cid])
    page.wait_for_timeout(1000)
    gid=page.evaluate("()=>window.__canvas.getState().groupNodes(['t1','t2'])")
    page.wait_for_timeout(800)
    page.evaluate("([g])=>window.__canvas.getState().setSelection([g])",[gid])
    page.wait_for_timeout(500)
    page.evaluate("""()=>{
        const el=document.querySelector('.pea-group-node-label');
        if(el){el.style.background='red'; el.style.color='white'; el.style.padding='10px 20px'; el.style.borderRadius='4px'; el.style.fontSize='24px'; el.style.zIndex='9999';}
    }""")
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(SHOTS,'debug_label_red.png'))
    b.close()
