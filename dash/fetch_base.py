#!/usr/bin/env python3
"""Lê a base GNPCP_BASE_2026 via Sheets API (conta de serviço) e grava base_grids.json.
Env: GOOGLE_SA_JSON (conteúdo do .json da conta de serviço)."""
import os, json
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID=os.environ.get('GNPCP_SSID','1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4')
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def col(i):
    r=''; i+=1
    while i: i,m=divmod(i-1,26); r=chr(65+m)+r
    return r
_ROWS={x['properties']['title']:x['properties']['gridProperties']['rowCount'] for x in s.get(B,params={'fields':'sheets.properties'}).json()['sheets']}
def grid(tab, ncol, nrows, chunk=8000):
    nrows=min(nrows,_ROWS.get(tab,nrows))   # limita ao tamanho real da aba
    out=[]
    for a in range(1,nrows+1,chunk):
        b=min(nrows,a+chunk-1)
        r=s.get(B+f"/values/{tab}!A{a}:{col(ncol-1)}{b}",params={"valueRenderOption":"UNFORMATTED_VALUE","dateTimeRenderOption":"SERIAL_NUMBER"})
        r.raise_for_status()
        v=r.json().get('values',[])
        v+= [[]]*(b-a+1-len(v))
        out+=v
    while out and not any(x not in ('',None) for x in out[-1]): out.pop()
    return out
dest={}
dest['CDO de Máquinas']=grid('CDO_MAQUINAS',64,90000)
dest['REND-Boletim de Produção']=grid('CDO_PRODUCAO',46,20000)
dest['FATURAMENTO_COMPILADO']=grid('FATURAMENTO_COMPILADO',26,1002)
dest['META X REALIZADO_CR1421']=grid('META_X_REALIZADO_CR1421',26,300)
dest['META_DE_PLANTIO_CR1421']=grid('META_PLANTIO_CR1421',26,300)
dest['CAD_TALHOES']=grid('CAD_TALHOES',9,20000)
json.dump(dest,open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'base_grids.json'),'w'))
print({k:len(v) for k,v in dest.items()})
