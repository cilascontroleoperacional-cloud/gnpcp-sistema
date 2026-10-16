#!/usr/bin/env python3
"""Diagnóstico (somente leitura): exporta abas da GNPCP_BASE_2026 para diag/out/*.json."""
import os, json
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
os.makedirs('diag/out',exist_ok=True)
def get(rng, render):
    r=s.get(B+f"/values/{rng}",params={"valueRenderOption":render,"dateTimeRenderOption":"SERIAL_NUMBER"}); r.raise_for_status()
    return r.json().get('values',[])
meta=s.get(B,params={"fields":"properties,sheets.properties"}).json()
json.dump(meta,open('diag/out/meta.json','w'))
out={}
for tab,rng in [('CDO_PRODUCAO','A1:AT12000'),('PRECOS','A1:H500'),('FATURAMENTO_COMPILADO','A1:T40'),('AGRUPAMENTOS','A1:E600'),('LOG','A1:D100')]:
    out[tab]={'v':get(f"{tab}!{rng}",'UNFORMATTED_VALUE'),'f':get(f"{tab}!{rng}",'FORMULA') if tab!='CDO_PRODUCAO' else get(f"{tab}!A1:AT12",'FORMULA')}
# fórmulas de algumas linhas espalhadas da produção
for a in (1000,3000,5000,7000,9000):
    out['CDO_PRODUCAO']['f_%d'%a]=get(f"CDO_PRODUCAO!A{a}:AT{a+2}",'FORMULA')
json.dump(out,open('diag/out/base.json','w'))
print({k:len(v['v']) for k,v in out.items()})
