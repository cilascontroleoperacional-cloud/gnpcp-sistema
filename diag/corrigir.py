#!/usr/bin/env python3
"""Correção 16/10/2026: PRECOS (52 chaves), 2 linhas CDO 46667, FATURAMENTO_COMPILADO linhas 13-22 em fórmula."""
import os, json, re
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
meta=s.get(B,params={"fields":"sheets(properties,basicFilter)"}).json()
sid={x['properties']['title']:x for x in meta['sheets']}
# backup do que será alterado
os.makedirs('diag/out',exist_ok=True)
json.dump({'PRECOS':get('PRECOS!A1:G500','FORMULA'),'FAT':get('FATURAMENTO_COMPILADO!A1:T25','FORMULA'),'PROD_tail':get('CDO_PRODUCAO!A9080:AT9100','FORMULA')},open('diag/out/backup.json','w'))
# 1) PRECOS
pv=get('PRECOS!A1:A1000'); last=len(pv)
chaves={r[0] for r in pv if r}
novos=[r for r in P['precos'] if r[0] not in chaves]
if novos:
    a=last+1; b=last+len(novos)
    put(f'PRECOS!A{a}:G{b}',novos,'RAW')
    g=sid['PRECOS']['properties']['sheetId']
    batch([{"copyPaste":{"source":{"sheetId":g,"startRowIndex":last-1,"endRowIndex":last,"startColumnIndex":0,"endColumnIndex":7},
            "destination":{"sheetId":g,"startRowIndex":a-1,"endRowIndex":b,"startColumnIndex":0,"endColumnIndex":7},"pasteType":"PASTE_FORMAT"}}])
print('PRECOS: +',len(novos))
# 2) CDO_PRODUCAO: 2 linhas do CDO 46667
pa=get('CDO_PRODUCAO!A1:A12000'); lastp=len(pa)
ex=get(f'CDO_PRODUCAO!A6:AR{lastp}')
chv={(r[43] if len(r)>43 else '') for r in ex}
def chave(r): return '|'.join(str(x) for x in [r[0],r[5],r[10],r[12],r[15],r[17],r[27],r[18],r[19],r[20]])
add=[r for r in P['prod_rows'] if chave(r) not in chv]
if add:
    ini=lastp+1
    linhas=[]
    for i,r in enumerate(add):
        n=ini+i
        f=[re.sub(r'(?<=[A-Z\$])%d\b'%P['tpl_row'],str(n),x) for x in P['tpl']]
        linhas.append(r+f+[chave(r),46311.45,'CORRECAO CLAUDE 16/10/2026 (Base_Fat_Rend)'])
    put(f'CDO_PRODUCAO!A{ini}:AT{ini+len(add)-1}',linhas,'USER_ENTERED')
    g=sid['CDO_PRODUCAO']['properties']['sheetId']
    reqs=[{"copyPaste":{"source":{"sheetId":g,"startRowIndex":lastp-1,"endRowIndex":lastp,"startColumnIndex":0,"endColumnIndex":46},
            "destination":{"sheetId":g,"startRowIndex":ini-1,"endRowIndex":ini-1+len(add),"startColumnIndex":0,"endColumnIndex":46},"pasteType":"PASTE_FORMAT"}}]
    bf=sid['CDO_PRODUCAO'].get('basicFilter')
    if bf:
        bf['range']['endRowIndex']=ini-1+len(add)
        reqs.append({"setBasicFilter":{"filter":bf}})
    batch(reqs)
print('CDO_PRODUCAO: +',len(add))
# 3) FATURAMENTO_COMPILADO linhas 13..22 em fórmula (mesmo padrão da linha 8)
vals=[]
for n in range(13,23):
    vals.append([f'=SUMIFS(CDO_PRODUCAO!$AI:$AI;CDO_PRODUCAO!$AG:$AG;FATURAMENTO_COMPILADO!$P{n};CDO_PRODUCAO!$D:$D;A{n})',
                 f'=(D{n}/N{n})*M{n}'])
put('FATURAMENTO_COMPILADO!D13:E22',vals)
put('FATURAMENTO_COMPILADO!G13:L22',[[f'=IFERROR(D{n}/F{n};"")',f'=IF(F{n}-D{n}<0;0;F{n}-D{n})',f'=D{n}/N{n}',f'=IFERROR(E{n}/F{n};"")',
     f'=IFERROR(IF(H{n}/O{n}<0;0;H{n}/O{n});0)',f'=(F{n}/M{n})*N{n}'] for n in range(13,23)])
print('FATURAMENTO: D13:L22 em fórmula')
# conferência
import time; time.sleep(5)
for r in get('FATURAMENTO_COMPILADO!A8:P22'): print(r[0],r[15],round(r[3],2) if isinstance(r[3],(int,float)) else r[3])
print('erros prod AH/AI:',sum(1 for r in get(f'CDO_PRODUCAO!AH6:AI{lastp+5}') if any(isinstance(x,str) and x.startswith('#') for x in r)))
