#!/usr/bin/env python3
"""Diagnóstico de lentidão (somente leitura): conta fórmulas por aba/coluna e referências a colunas inteiras."""
import os, json, re, collections
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
meta=s.get(B,params={"fields":"sheets(properties,conditionalFormats,protectedRanges,basicFilter),namedRanges"}).json()
os.makedirs('diag/out',exist_ok=True)
rep={'abas':[]}
def col(i):
    r=''; i+=1
    while i: i,m=divmod(i-1,26); r=chr(65+m)+r
    return r
for sh in meta['sheets']:
    p=sh['properties']; t=p['title']; g=p['gridProperties']; R,C=g['rowCount'],g['columnCount']
    info={'aba':t,'linhas_grade':R,'colunas_grade':C,'celulas_grade':R*C,'cond_formats':len(sh.get('conditionalFormats',[]))}
    nf=0; porcol=collections.Counter(); amostra={}; colint=collections.Counter(); funcs=collections.Counter(); usadas=0
    for a in range(1,R+1,10000):
        b=min(R,a+9999)
        r=s.get(B+f"/values/'{t}'!A{a}:{col(C-1)}{b}",params={"valueRenderOption":"FORMULA"}); r.raise_for_status()
        for i,row in enumerate(r.json().get('values',[])):
            if any(x not in ('',None) for x in row): usadas=a+i
            for j,x in enumerate(row):
                if isinstance(x,str) and x.startswith('='):
                    nf+=1; porcol[col(j)]+=1
                    if col(j) not in amostra: amostra[col(j)]=x[:220]
                    if re.search(r"(?<![A-Z0-9\$])\$?[A-Z]{1,3}:\$?[A-Z]{1,3}(?![0-9])",x): colint[col(j)]+=1
                    for fn in re.findall(r'([A-Z][A-Z0-9\.]+)\(',x): funcs[fn]+=1
    info.update(ultima_linha_usada=usadas,formulas=nf,por_coluna=dict(porcol.most_common()),col_inteira=dict(colint),funcoes=dict(funcs.most_common(15)),amostra=amostra)
    rep['abas'].append(info); print(t,R,C,'formulas',nf,'colInteira',sum(colint.values()),'cf',info['cond_formats'])
json.dump(rep,open('diag/out/lentidao.json','w'),ensure_ascii=False,indent=1)
