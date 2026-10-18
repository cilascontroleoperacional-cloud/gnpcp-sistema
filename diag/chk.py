import os, json, datetime, collections
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":"UNFORMATTED_VALUE"}); x.raise_for_status(); return x.json().get('values',[])
def d(n): return (datetime.date(1899,12,30)+datetime.timedelta(days=int(n))).strftime('%d/%m') if isinstance(n,(int,float)) else n
P=get('CDO_PRODUCAO!A6:AT12000'); M=get('CDO_MAQUINAS!A9:AT70000'); C=get('CAD_TALHOES!A1:I30000')
print('PROD fazendas PINH:',collections.Counter((r[3],r[15],r[16]) for r in P if len(r)>16 and 'PINH' in str(r[16]).upper()))
print('MAQ fazendas PINH:',collections.Counter((r[3],r[17],r[18]) for r in M if len(r)>18 and 'PINH' in str(r[18]).upper()))
print('CAD PINH:',collections.Counter((r[0],r[1],r[2]) for r in C[1:] if len(r)>2 and 'PINH' in str(r[2]).upper()))
print('PROD talhão 399:',collections.Counter((r[3],r[15],r[16]) for r in P if len(r)>17 and str(r[17])=='399'))
print('MAQ talhão 399:',collections.Counter((r[3],r[17],r[18]) for r in M if len(r)>19 and str(r[19])=='399'))
print('CAD talhão 399:',[r[:6] for r in C[1:] if len(r)>3 and str(r[3])=='399'])
for r in P:
    r=r+['']*46
    if 'PINH' in str(r[16]).upper(): print('P',r[0],d(r[1]),r[3],r[15],r[16],'| tal',repr(r[17]),'|',r[13][:40],'| prod',r[19],r[27],'|',r[32])
