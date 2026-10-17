import os, json, time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def put(r,v):
    x=s.put(B+f"/values/{r}",params={"valueInputOption":"USER_ENTERED"},json={"values":v}); x.raise_for_status()
def get(r):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":"UNFORMATTED_VALUE"}); x.raise_for_status(); return x.json().get('values',[])
P='CDO_PRODUCAO!'
put('FOLLOWUP_OPERACOES!D6',[['=IFERROR(LET(L;SORT(UNIQUE(FILTER('+P+'$N$6:$N;'+P+'$D$6:$D=$B$2;'+P+'$Q$6:$Q=$B$3;'+P+'$AB$6:$AB="Principal";'+P+'$T$6:$T>0;LEFT(UPPER('+P+'$N$6:$N);13)<>"APOIO E MANUT")));SPLIT(TEXTJOIN("§";TRUE;ARRAYFORMULA(L&"§"&L));"§";FALSE;TRUE));"")']])
U='XLOOKUP(D6:CZ6;'+P+'$N$6:$N;'+P+'$O$6:$O;"")'
NM='IF(LEN(D6:CZ6)>48;LEFT(D6:CZ6;46)&"…";D6:CZ6)'
put('FOLLOWUP_OPERACOES!D7',[['=ARRAYFORMULA(IF(D6:CZ6="";"";IF(ISODD(COLUMN(D6:CZ6)-3);'+NM+'&" ("&'+U+'&")";IF('+U+'="HA";"%";"—"))))']])
time.sleep(8)
for r in get('FOLLOWUP_OPERACOES!A5:O9'): print(r)
