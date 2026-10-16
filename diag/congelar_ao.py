#!/usr/bin/env python3
"""Congela em valores a coluna AO (% Perdas) da CDO_MAQUINAS nas linhas de histórico (fora das 3 competências vivas)."""
import os, json, time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r,m='UNFORMATTED_VALUE'):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":m}); x.raise_for_status(); return x.json().get('values',[])
VIVAS={'Agosto-26','Setembro-26','Outubro-26'}
comp=get('CDO_MAQUINAS!AW9:AW60000'); n=len(comp)
fo=get(f'CDO_MAQUINAS!AO9:AO{8+n}','FORMULA'); va=get(f'CDO_MAQUINAS!AO9:AO{8+n}')
an3=get('CDO_MAQUINAS!AN3')[0][0]; print('AN3 antes',an3)
alvo=[]
for i in range(n):
    cp=comp[i][0] if comp[i] else ''
    f=fo[i][0] if i<len(fo) and fo[i] else ''
    if cp not in VIVAS and isinstance(f,str) and f.startswith('='):
        v=va[i][0] if i<len(va) and va[i] else ''
        alvo.append((i+9,v))
print('linhas a congelar',len(alvo))
blocos=[]
for r,v in alvo:
    if blocos and blocos[-1][0]+len(blocos[-1][1])==r: blocos[-1][1].append([v])
    else: blocos.append([r,[[v]]])
data=[{"range":f"CDO_MAQUINAS!AO{r}:AO{r+len(vs)-1}","values":vs} for r,vs in blocos]
for k in range(0,len(data),200):
    x=s.post(B+"/values:batchUpdate",json={"valueInputOption":"RAW","data":data[k:k+200]}); x.raise_for_status()
print('blocos',len(blocos))
time.sleep(5)
fo2=get(f'CDO_MAQUINAS!AO9:AO{8+n}','FORMULA'); va2=get(f'CDO_MAQUINAS!AO9:AO{8+n}')
nf=sum(1 for r in fo2 if r and isinstance(r[0],str) and r[0].startswith('='))
dif=sum(1 for i in range(n) if (va[i][0] if i<len(va) and va[i] else '')!=(va2[i][0] if i<len(va2) and va2[i] else ''))
print('fórmulas AO restantes',nf,'| valores alterados',dif,'| AN3 depois',get('CDO_MAQUINAS!AN3')[0][0])
