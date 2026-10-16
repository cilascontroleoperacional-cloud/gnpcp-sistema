#!/usr/bin/env python3
"""Competências vivas 3 -> 2: congela em valores as linhas de Agosto-26 (e anteriores, se ainda houver fórmula)
nas colunas calculadas de CDO_MAQUINAS (AM:BB) e CDO_PRODUCAO (AG:AQ). Confere totais antes/depois."""
import os, json, time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r,m='UNFORMATTED_VALUE'):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":m}); x.raise_for_status(); return x.json().get('values',[])
VIVAS={'Setembro-26','Outubro-26'}
def checks():
    return {'MAQ_painel':get('CDO_MAQUINAS!AN3:AS4'),'PROD_AI4':get('CDO_PRODUCAO!AI4'),'FAT':[r[3] for r in get('FATURAMENTO_COMPILADO!A8:D22')]}
antes=checks(); print('antes',json.dumps(antes)[:400])
def congelar(aba,h,ccomp,c0,c1,L0,L1):
    comp=get(f'{aba}!{ccomp}{h+1}:{ccomp}{h+70000}'); n=len(comp)
    fo=get(f'{aba}!{L0}{h+1}:{L1}{h+n}','FORMULA'); va=get(f'{aba}!{L0}{h+1}:{L1}{h+n}')
    w=c1-c0+1; linhas=[]
    for i in range(n):
        cp=comp[i][0] if comp[i] else ''
        if cp in VIVAS or cp=='': continue
        f=(fo[i] if i<len(fo) else [])+['']*w
        if any(isinstance(x,str) and x.startswith('=') for x in f[:w]):
            v=(va[i] if i<len(va) else [])+['']*w
            linhas.append((h+1+i,v[:w]))
    blocos=[]
    for r,v in linhas:
        if blocos and blocos[-1][0]+len(blocos[-1][1])==r: blocos[-1][1].append(v)
        else: blocos.append([r,[v]])
    data=[]
    for r,vs in blocos:
        for k in range(0,len(vs),4000):
            part=vs[k:k+4000]; data.append({"range":f"{aba}!{L0}{r+k}:{L1}{r+k+len(part)-1}","values":part})
    for k in range(0,len(data),20):
        x=s.post(B+"/values:batchUpdate",json={"valueInputOption":"RAW","data":data[k:k+20]}); x.raise_for_status()
    print(aba,'linhas congeladas',len(linhas),'em',len(blocos),'bloco(s)')
congelar('CDO_MAQUINAS',8,'AW',38,53,'AM','BB')
congelar('CDO_PRODUCAO',5,'AG',32,42,'AG','AQ')
time.sleep(8)
depois=checks(); print('depois',json.dumps(depois)[:400]); print('IGUAL' if antes==depois else 'DIFERENTE')
# contagem de fórmulas restantes
for aba,rng in (('CDO_MAQUINAS','AM9:BB60000'),('CDO_PRODUCAO','AG6:AQ12000')):
    f=get(f'{aba}!{rng}','FORMULA'); print(aba,'fórmulas restantes',sum(1 for r in f for x in r if isinstance(x,str) and x.startswith('=')))
