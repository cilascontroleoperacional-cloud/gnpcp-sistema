import os, json, datetime
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
x=s.get(B+"/values/CDO_PRODUCAO!A6:AT12000",params={"valueRenderOption":"UNFORMATTED_VALUE"}); v=x.json()['values']
def d(n): return (datetime.date(1899,12,30)+datetime.timedelta(days=int(n))).strftime('%d/%m') if isinstance(n,(int,float)) else n
for i,r in enumerate(v):
    r=r+['']*46
    if str(r[16])=='TERRA SANTA -' and str(r[17])=='9':
        print(i+6,'|',r[0],d(r[1]),'|',r[5][:18],'|',r[10][:22],'|',r[12],r[13][:40],'| HT',r[18],'PROD',r[19],'HI',r[20],'|',r[27],'|',r[26],'| Fonte',r[45])
