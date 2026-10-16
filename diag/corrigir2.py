#!/usr/bin/env python3
"""Correção 2 (16/10/2026): realinha a coluna Chave (AR) do lote 'COLAGEM 16/10/2026 09:56' e inclui as 2 linhas do CDO 46667 GN1410."""
import os, json, re, time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
P=json.load(open('diag/plan.json'))
def get(rng,render='UNFORMATTED_VALUE'):
    r=s.get(B+f"/values/{rng}",params={"valueRenderOption":render}); r.raise_for_status(); return r.json().get('values',[])
def put(rng,vals,opt='USER_ENTERED'):
    r=s.put(B+f"/values/{rng}",params={"valueInputOption":opt},json={"values":vals}); r.raise_for_status(); return r.json()
def batch(reqs):
    r=s.post(B+":batchUpdate",json={"requests":reqs}); r.raise_for_status(); return r.json()
def fmt(x):
    if isinstance(x,float) and x.is_integer(): x=int(x)
    return str(x)
def chave(r): return '|'.join(fmt(r[i]) if i<len(r) else '' for i in [0,5,10,12,15,17,27,18,19,20])
meta=s.get(B,params={"fields":"sheets(properties,basicFilter)"}).json()
sh={x['properties']['title']:x for x in meta['sheets']}['CDO_PRODUCAO']; g=sh['properties']['sheetId']
V=get('CDO_PRODUCAO!A1:AT12000'); last=len(V)
while last>5 and (not V[last-1] or V[last-1][0] in ('',None)): last-=1
# 1) realinhar AR do lote 09:56
upd=[]
for i in range(5,last):
    r=V[i]+['']*(46-len(V[i]))
    if r[45]=='COLAGEM 16/10/2026 09:56' and r[43]!=chave(r): upd.append((i+1,chave(r)))
# grava em blocos contíguos
blocos=[]
for n,k in upd:
    if blocos and blocos[-1][0]+len(blocos[-1][1])==n: blocos[-1][1].append([k])
    else: blocos.append([n,[[k]]])
for n,vals in blocos: put(f'CDO_PRODUCAO!AR{n}:AR{n+len(vals)-1}',vals,'RAW')
print('Chave realinhada:',len(upd),'linhas em',len(blocos),'bloco(s)')
# 2) linhas do CDO 46667 que faltam (compara pelos valores, não pela Chave)
existe={chave(V[i]+['']*46) for i in range(5,last)}
add=[r for r in P['prod_rows'] if chave(r) not in existe]
if add:
    ini=last+1; linhas=[]
    for j,r in enumerate(add):
        n=ini+j
        f=[re.sub(r'(?<=[A-Z\$])%d\b'%P['tpl_row'],str(n),x) for x in P['tpl']]
        linhas.append(r+f+[chave(r),46311.45,'CORRECAO CLAUDE 16/10/2026 (Base_Fat_Rend)'])
    put(f'CDO_PRODUCAO!A{ini}:AT{ini+len(add)-1}',linhas)
    reqs=[{"copyPaste":{"source":{"sheetId":g,"startRowIndex":last-1,"endRowIndex":last,"startColumnIndex":0,"endColumnIndex":46},
           "destination":{"sheetId":g,"startRowIndex":ini-1,"endRowIndex":ini-1+len(add),"startColumnIndex":0,"endColumnIndex":46},"pasteType":"PASTE_FORMAT"}}]
    bf=sh.get('basicFilter')
    if bf: bf['range']['endRowIndex']=ini-1+len(add); reqs.append({"setBasicFilter":{"filter":bf}})
    batch(reqs)
print('Linhas incluídas:',len(add))
time.sleep(4)
for r in get(f'CDO_PRODUCAO!A{last+1}:AI{last+len(add)}'): print('  ',r[0],r[3],r[13],r[17],r[32],r[33],r[34])
for r in get('FATURAMENTO_COMPILADO!A8:P22'): print(r[0],r[15],round(r[3],2))
