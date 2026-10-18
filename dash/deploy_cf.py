#!/usr/bin/env python3
"""Publica os 4 dashboards (Workers com assets) via API do Cloudflare.
Uso: python3 deploy_cf.py [--dry]   |  env CF_API_TOKEN e CF_ACCOUNT_ID (segredos do GitHub)."""
import sys, os, json, hashlib, base64, requests
HERE=os.path.dirname(os.path.abspath(__file__))
TOKEN=os.environ['CF_API_TOKEN']; ACC=os.environ['CF_ACCOUNT_ID']
API=f"https://api.cloudflare.com/client/v4/accounts/{ACC}"
MAPA={'gn-ms':'indicadores-gestao-gnms','lacan-arauco':'gnms-indicadores-pcp','pcm-lacan':'indicadores-mecanicos-gn-ms','cr1421':'pcpgn-dash-cr1421','followup':'gn-followup-talhoes'}
DRY='--dry' in sys.argv
H={'Authorization':f'Bearer {TOKEN}'}
def hsh(b): return hashlib.sha256((base64.b64encode(b).decode()+'html').encode()).hexdigest()[:32]
def deploy(var,name):
    content=open(os.path.join(HERE,'out_base',var+'.html'),'rb').read()
    h=hsh(content); manifest={'/index.html':{'hash':h,'size':len(content)}}
    print(f'{var} -> {name}: {len(content)/1048576:.2f} MB hash {h}')
    if DRY: return
    r=requests.post(f'{API}/workers/scripts/{name}/assets-upload-session',headers=H,json={'manifest':manifest}); r.raise_for_status()
    res=r.json()['result']; jwt=res['jwt']; buckets=res.get('buckets') or []
    if buckets:
        files={h:(h,base64.b64encode(content).decode(),'text/html')}
        r=requests.post(f'{API}/workers/assets/upload?base64=true',headers={'Authorization':f'Bearer {jwt}'},files=files); r.raise_for_status()
        jwt=r.json()['result']['jwt']
    meta={'assets':{'jwt':jwt,'config':{'html_handling':'auto-trailing-slash','not_found_handling':'none'}},'compatibility_date':'2026-10-15'}
    r=requests.put(f'{API}/workers/scripts/{name}',headers=H,files={'metadata':(None,json.dumps(meta),'application/json')})
    print('   PUT',r.status_code, r.text[:300] if r.status_code!=200 else 'ok')
    r.raise_for_status()
    # garante o endereço público <nome>.<subdominio>.workers.dev (idempotente; necessário para workers novos)
    r=requests.post(f'{API}/workers/scripts/{name}/subdomain',headers=H,json={'enabled':True,'previews_enabled':False})
    print('   workers.dev',r.status_code)
for v,n in MAPA.items():
    if os.path.exists(os.path.join(HERE,'out_base',v+'.html')): deploy(v,n)
