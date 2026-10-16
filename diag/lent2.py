import os, json
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r,m='FORMULA'):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":m}); x.raise_for_status(); return x.json().get('values',[])
out={'maq_hdr':get('CDO_MAQUINAS!A8:BL8','UNFORMATTED_VALUE'),'maq_10':get('CDO_MAQUINAS!A10:BL10'),'maq_40000':get('CDO_MAQUINAS!A40000:BL40000'),
     'maq_comp':get('CDO_MAQUINAS!AW9:AW58000','UNFORMATTED_VALUE'),'dm':get('DM!A1:AM20'),'dm_ad':get('DM!AD14:AD100','UNFORMATTED_VALUE'),
     'meta':get('META_X_REALIZADO_CR1421!A1:O22')}
os.makedirs('diag/out',exist_ok=True); json.dump(out,open('diag/out/lent2.json','w'),ensure_ascii=False)
print('ok')
