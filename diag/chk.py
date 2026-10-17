import os, json
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r,m='UNFORMATTED_VALUE'):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":m}); x.raise_for_status(); return x.json().get('values',[])
print('ROW6',[x[:25] for x in get('FOLLOWUP_OPERACOES!D6:CZ6')[0]])
v=get('CDO_PRODUCAO!A6:AQ12000')
n=0
for r in v:
    r=r+['']*45
    if str(r[16])=='TERRA SANTA -' and 'SUBSOL' in str(r[13]).upper():
        n+=1
        if n<4: print(repr(r[3]),repr(r[13]),repr(r[19]),repr(r[27]))
print('subsol rows',n)
