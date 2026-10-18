#!/usr/bin/env python3
"""Cadastro 'FAZENDA TRÊS SELENAS' pertence ao GN1270 (Tres Selenas, cód. 1267), não ao GN1400/852."""
import os, json, datetime
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":"UNFORMATTED_VALUE"}); x.raise_for_status(); return x.json().get('values',[])
v=get('CAD_TALHOES!A1:I30000'); cab=v[0]; rows=[r+['']*(9-len(r)) for r in v[1:] if r]
hoje=datetime.date.today().strftime('%d/%m/%Y')
ts=json.load(open('diag/tres_selenas.json'))
# 1) desfaz cadastro aplicado em GN1400/852
n1=0
for r in rows:
    if r[0]=='GN1400' and str(r[1])=='852' and r[5]=='CADASTRO':
        r[7]=''; r[4]=r[6] if r[6]!='' else ''; r[5]='CDOxBMS' if r[6]!='' else 'SEM ÁREA'; r[8]=hoje; n1+=1
# remove linhas de GN1400/852 criadas só pelo cadastro (sem BMS e sem produção conhecida não dá p/ saber -> mantém só se tinha BMS)
antes=len(rows)
rows=[r for r in rows if not (r[0]=='GN1400' and str(r[1])=='852' and r[5]=='SEM ÁREA' and r[6]=='')]
# 2) aplica em GN1270/1267
idx={(r[0],str(r[1]),str(r[3])):r for r in rows}
nome=next((r[2] for r in rows if r[0]=='GN1270' and str(r[1])=='1267'),'Tres Selenas')
add=upd=0
for tal,area in ts:
    k=('GN1270','1267',str(tal))
    if k in idx: r=idx[k]; r[7]=area; r[4]=area; r[5]='CADASTRO'; r[8]=hoje; upd+=1
    else: rows.append(['GN1270',1267,nome,tal,area,'CADASTRO','',area,hoje]); add+=1
def sk(x): return (x[0],str(x[2]).upper(),0 if isinstance(x[3],int) else 1,x[3] if isinstance(x[3],int) else 0,str(x[3]))
rows.sort(key=sk)
x=s.post(B+"/values:batchClear",json={"ranges":["CAD_TALHOES!A2:I30000"]}); x.raise_for_status()
x=s.put(B+f"/values/CAD_TALHOES!A2:I{len(rows)+1}",params={"valueInputOption":"RAW"},json={"values":rows}); x.raise_for_status()
print('GN1400/852 desfeitos',n1,'| removidas',antes-len(rows),'| GN1270/1267 atualizados',upd,'incluídos',add,'| total',len(rows),'| nome',nome)
print([r for r in rows if r[0]=='GN1270' and str(r[1])=='1267'][:5])
