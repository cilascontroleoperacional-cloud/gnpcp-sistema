#!/usr/bin/env python3
"""17/10/2026: (1) talhões convertidos em data -> texto DD-MM; (2) aba CAD_TALHOES; (3) aba FOLLOWUP_OPERACOES (fórmulas)."""
import os, json, time, datetime
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
SSID='1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4'
c=service_account.Credentials.from_service_account_info(json.loads(os.environ['GOOGLE_SA_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
s=AuthorizedSession(c); B=f"https://sheets.googleapis.com/v4/spreadsheets/{SSID}"
def get(r,m='UNFORMATTED_VALUE'):
    x=s.get(B+f"/values/{r}",params={"valueRenderOption":m}); x.raise_for_status(); return x.json().get('values',[])
def put(r,v,opt='USER_ENTERED'):
    x=s.put(B+f"/values/{r}",params={"valueInputOption":opt},json={"values":v}); x.raise_for_status()
def batch(reqs):
    x=s.post(B+":batchUpdate",json={"requests":reqs})
    if x.status_code>=400: print(x.text[:2000]); x.raise_for_status()
    return x.json()
def sheets():
    return {sh['properties']['title']:sh['properties'] for sh in s.get(B,params={"fields":"sheets.properties"}).json()['sheets']}
def col(i):
    r=''; i+=1
    while i: i,m=divmod(i-1,26); r=chr(65+m)+r
    return r
# ── 1) talhões que viraram data ──
def fix(aba,h,L):
    v=get(f'{aba}!{L}{h+1}:{L}70000'); upd=[]
    for i,r in enumerate(v):
        x=r[0] if r else ''
        if isinstance(x,(int,float)) and 45658<=x<=46752:
            d=datetime.date(1899,12,30)+datetime.timedelta(days=int(x)); upd.append((h+1+i,d.strftime('%d-%m')))
    data=[{"range":f"{aba}!{L}{n}","values":[[t]]} for n,t in upd]
    for k in range(0,len(data),500):
        x=s.post(B+"/values:batchUpdate",json={"valueInputOption":"RAW","data":data[k:k+500]}); x.raise_for_status()
    # formato texto para não reconverter
    print(aba,'talhões corrigidos',len(upd),sorted(set(t for _,t in upd)))
fix('CDO_PRODUCAO',5,'R'); fix('CDO_MAQUINAS',8,'T')
# ── 2) CAD_TALHOES ──
rows=json.load(open('diag/cad_rows.json'))
sh=sheets()
reqs=[]
for nome,rc,cc in (('CAD_TALHOES',len(rows)+50,10),('FOLLOWUP_OPERACOES',320,110)):
    if nome in sh: reqs.append({"deleteSheet":{"sheetId":sh[nome]['sheetId']}})
    reqs.append({"addSheet":{"properties":{"title":nome,"gridProperties":{"rowCount":rc,"columnCount":cc,"hideGridlines":True}}}})
batch(reqs); sh=sheets(); gC=sh['CAD_TALHOES']['sheetId']; gF=sh['FOLLOWUP_OPERACOES']['sheetId']
hoje=datetime.date.today().strftime('%d/%m/%Y')
cab=['CR','Cód. Projeto','Fazenda','Talhão','Área (ha)','Origem','Área CDOxBMS','Área Cadastro','Atualizado em']
put(f'CAD_TALHOES!A1:I{len(rows)+1}',[cab]+[r+[hoje] for r in rows],'RAW')
azul={"red":0x1F/255,"green":0x38/255,"blue":0x64/255}; zebra={"red":0xDC/255,"green":0xE6/255,"blue":0xF1/255}; branco={"red":1,"green":1,"blue":1}
def cabfmt(g,r0,c0,c1):
    return {"repeatCell":{"range":{"sheetId":g,"startRowIndex":r0,"endRowIndex":r0+1,"startColumnIndex":c0,"endColumnIndex":c1},
        "cell":{"userEnteredFormat":{"backgroundColor":azul,"textFormat":{"foregroundColor":branco,"bold":True},"horizontalAlignment":"CENTER","verticalAlignment":"MIDDLE","wrapStrategy":"WRAP"}},
        "fields":"userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)"}}
batch([cabfmt(gC,0,0,9),
 {"updateSheetProperties":{"properties":{"sheetId":gC,"gridProperties":{"frozenRowCount":1}},"fields":"gridProperties.frozenRowCount"}},
 {"setBasicFilter":{"filter":{"range":{"sheetId":gC,"startRowIndex":0,"endRowIndex":len(rows)+1,"startColumnIndex":0,"endColumnIndex":9}}}},
 {"addBanding":{"bandedRange":{"range":{"sheetId":gC,"startRowIndex":1,"endRowIndex":len(rows)+1,"startColumnIndex":0,"endColumnIndex":9},
   "rowProperties":{"firstBandColor":branco,"secondBandColor":zebra}}}},
 {"repeatCell":{"range":{"sheetId":gC,"startRowIndex":1,"startColumnIndex":3,"endColumnIndex":4},"cell":{"userEnteredFormat":{"horizontalAlignment":"CENTER"}},"fields":"userEnteredFormat.horizontalAlignment"}},
 {"repeatCell":{"range":{"sheetId":gC,"startRowIndex":1,"startColumnIndex":4,"endColumnIndex":8},"cell":{"userEnteredFormat":{"numberFormat":{"type":"NUMBER","pattern":"#,##0.00"}}},"fields":"userEnteredFormat.numberFormat"}},
 {"updateDimensionProperties":{"range":{"sheetId":gC,"dimension":"COLUMNS","startIndex":2,"endIndex":3},"properties":{"pixelSize":260},"fields":"pixelSize"}}])
print('CAD_TALHOES linhas',len(rows))
# ── 3) FOLLOWUP_OPERACOES ──
P='CDO_PRODUCAO!'
F={}
F['A1']=[['FOLLOW-UP DE OPERAÇÕES POR TALHÃO']]
F['A2:B4']=[['CR','GN1400'],['Fazenda','TERRA SANTA -'],['Competência','(Todas)']]
F['D2']=[['Realizado = soma da Produção (Tipo Recurso = Principal) por talhão e operação · % = Realizado ÷ Área do talhão (só operações em HA) · Áreas: aba CAD_TALHOES']]
F['A5:C5']=[['TOTAL','','=SUM(C8:C320)']]
F['A7:C7']=[['Talhão','Cód. Projeto','Área (ha)']]
F['A8']=[['=IFERROR(SORT(FILTER(HSTACK(CAD_TALHOES!D2:D;CAD_TALHOES!B2:B;CAD_TALHOES!E2:E);CAD_TALHOES!A2:A=$B$2;CAD_TALHOES!C2:C=$B$3);1;TRUE);"")']]
F['D6']=[['=IFERROR(LET(L;SORT(UNIQUE(FILTER('+P+'$N$6:$N;'+P+'$D$6:$D=$B$2;'+P+'$Q$6:$Q=$B$3;'+P+'$AB$6:$AB="Principal";'+P+'$T$6:$T>0)));SPLIT(TEXTJOIN("§";TRUE;ARRAYFORMULA(L&"§"&L));"§";FALSE;TRUE));"")']]
U='XLOOKUP(D6:CZ6;'+P+'$N$6:$N;'+P+'$O$6:$O;"")'
F['D7']=[['=ARRAYFORMULA(IF(D6:CZ6="";"";IF(ISODD(COLUMN(D6:CZ6)-3);D6:CZ6&" ("&'+U+'&")";IF('+U+'="HA";"%";"—"))))']]
F['D8']=[['=IFERROR(ARRAYFORMULA(LET(comp;IF($B$4="(Todas)";"";$B$4);'
 'cond;('+P+'$D$6:$D=$B$2)*('+P+'$Q$6:$Q=$B$3)*('+P+'$AB$6:$AB="Principal")*(((comp="")+('+P+'$AG$6:$AG=comp))>0);'
 'fc;FILTER('+P+'$P$6:$P;cond);ft;FILTER('+P+'$R$6:$R;cond);fo;FILTER('+P+'$N$6:$N;cond);fp;IFERROR(FILTER('+P+'$T$6:$T;cond)*1;0);'
 'ta;FILTER($A$8:$A$320;$A$8:$A$320<>"");cb;FILTER($B$8:$B$320;$A$8:$A$320<>"");ar;FILTER($C$8:$C$320;$A$8:$A$320<>"");'
 'acts;FILTER($D$6:$CZ$6;$D$6:$CZ$6<>"");lab;FILTER($D$7:$CZ$7;$D$6:$CZ$6<>"");'
 'MAKEARRAY(ROWS(ta);COLUMNS(acts);LAMBDA(i;j;LET(r;SUMPRODUCT((fc=INDEX(cb;i))*(ft=INDEX(ta;i))*(fo=INDEX(acts;1;j))*fp);'
 'IF(ISODD(j);IF(r=0;"";r);IF(INDEX(lab;1;j)="%";IF(OR(INDEX(ar;i)="";r=0);"";r/INDEX(ar;i));"")))))));"")']]
tot=[]
for j in range(3,104):
    L=col(j)
    if (j-3)%2==0: tot.append(f'=IF({L}$6="";"";SUM({L}8:{L}320))')
    else: P_=col(j-1); tot.append(f'=IF({L}$7="%";IFERROR({P_}5/$C$5;"");"")')
F['D5:CZ5']=[tot]
F['DB1']=[['=IFERROR(SORT(UNIQUE(FILTER(CAD_TALHOES!C2:C;CAD_TALHOES!A2:A=$B$2)));"")']]
F['DC1']=[['=VSTACK("(Todas)";SORT(UNIQUE(FILTER('+P+'AG6:AG;'+P+'AG6:AG<>""))))']]
for rng,val in F.items(): put('FOLLOWUP_OPERACOES!'+rng,val)
amarelo={"red":1,"green":0.92,"blue":0.61}; verde={"red":0.78,"green":0.94,"blue":0.81}; ama2={"red":1,"green":0.95,"blue":0.8}
reqs=[cabfmt(gF,6,0,104),
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":0,"endRowIndex":1,"startColumnIndex":0,"endColumnIndex":1},"cell":{"userEnteredFormat":{"textFormat":{"bold":True,"fontSize":14,"foregroundColor":azul}}},"fields":"userEnteredFormat.textFormat"}},
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":1,"endRowIndex":4,"startColumnIndex":0,"endColumnIndex":1},"cell":{"userEnteredFormat":{"textFormat":{"bold":True}}},"fields":"userEnteredFormat.textFormat"}},
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":1,"endRowIndex":4,"startColumnIndex":1,"endColumnIndex":2},"cell":{"userEnteredFormat":{"backgroundColor":amarelo,"textFormat":{"bold":True}}},"fields":"userEnteredFormat(backgroundColor,textFormat)"}},
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":1,"endRowIndex":2,"startColumnIndex":3,"endColumnIndex":4},"cell":{"userEnteredFormat":{"textFormat":{"italic":True,"fontSize":9,"foregroundColor":{"red":0.4,"green":0.4,"blue":0.4}}}},"fields":"userEnteredFormat.textFormat"}},
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":4,"endRowIndex":5,"startColumnIndex":0,"endColumnIndex":104},"cell":{"userEnteredFormat":{"backgroundColor":azul,"textFormat":{"foregroundColor":branco,"bold":True}}},"fields":"userEnteredFormat(backgroundColor,textFormat)"}},
 {"updateDimensionProperties":{"range":{"sheetId":gF,"dimension":"ROWS","startIndex":5,"endIndex":6},"properties":{"hiddenByUser":True},"fields":"hiddenByUser"}},
 {"updateDimensionProperties":{"range":{"sheetId":gF,"dimension":"ROWS","startIndex":6,"endIndex":7},"properties":{"pixelSize":70},"fields":"pixelSize"}},
 {"updateDimensionProperties":{"range":{"sheetId":gF,"dimension":"COLUMNS","startIndex":105,"endIndex":107},"properties":{"hiddenByUser":True},"fields":"hiddenByUser"}},
 {"updateDimensionProperties":{"range":{"sheetId":gF,"dimension":"COLUMNS","startIndex":0,"endIndex":1},"properties":{"pixelSize":95},"fields":"pixelSize"}},
 {"updateDimensionProperties":{"range":{"sheetId":gF,"dimension":"COLUMNS","startIndex":1,"endIndex":2},"properties":{"pixelSize":190},"fields":"pixelSize"}},
 {"updateSheetProperties":{"properties":{"sheetId":gF,"gridProperties":{"frozenRowCount":7,"frozenColumnCount":3}},"fields":"gridProperties(frozenRowCount,frozenColumnCount)"}},
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":4,"endRowIndex":320,"startColumnIndex":0,"endColumnIndex":2},"cell":{"userEnteredFormat":{"horizontalAlignment":"CENTER"}},"fields":"userEnteredFormat.horizontalAlignment"}},
 {"repeatCell":{"range":{"sheetId":gF,"startRowIndex":4,"endRowIndex":320,"startColumnIndex":2,"endColumnIndex":3},"cell":{"userEnteredFormat":{"numberFormat":{"type":"NUMBER","pattern":"#,##0.00"}}},"fields":"userEnteredFormat.numberFormat"}},
 {"setDataValidation":{"range":{"sheetId":gF,"startRowIndex":1,"endRowIndex":2,"startColumnIndex":1,"endColumnIndex":2},"rule":{"condition":{"type":"ONE_OF_LIST","values":[{"userEnteredValue":x} for x in ["GN1270","GN1400","GN1410","GN1421","GN1430"]]},"showCustomUi":True,"strict":True}}},
 {"setDataValidation":{"range":{"sheetId":gF,"startRowIndex":2,"endRowIndex":3,"startColumnIndex":1,"endColumnIndex":2},"rule":{"condition":{"type":"ONE_OF_RANGE","values":[{"userEnteredValue":"=$DB$1:$DB$400"}]},"showCustomUi":True,"strict":False}}},
 {"setDataValidation":{"range":{"sheetId":gF,"startRowIndex":3,"endRowIndex":4,"startColumnIndex":1,"endColumnIndex":2},"rule":{"condition":{"type":"ONE_OF_RANGE","values":[{"userEnteredValue":"=$DC$1:$DC$60"}]},"showCustomUi":True,"strict":False}}},
 {"addBanding":{"bandedRange":{"range":{"sheetId":gF,"startRowIndex":7,"endRowIndex":320,"startColumnIndex":0,"endColumnIndex":104},"rowProperties":{"firstBandColor":branco,"secondBandColor":zebra}}}}]
for j in range(3,104):
    pct=(j-3)%2==1
    reqs.append({"repeatCell":{"range":{"sheetId":gF,"startRowIndex":4,"endRowIndex":320,"startColumnIndex":j,"endColumnIndex":j+1},
      "cell":{"userEnteredFormat":{"horizontalAlignment":"CENTER","numberFormat":{"type":"PERCENT","pattern":"0%"} if pct else {"type":"NUMBER","pattern":"#,##0.00"}}},
      "fields":"userEnteredFormat(horizontalAlignment,numberFormat)"}})
    reqs.append({"updateDimensionProperties":{"range":{"sheetId":gF,"dimension":"COLUMNS","startIndex":j,"endIndex":j+1},"properties":{"pixelSize":60 if pct else 150},"fields":"pixelSize"}})
rng={"sheetId":gF,"startRowIndex":7,"endRowIndex":320,"startColumnIndex":3,"endColumnIndex":104}
reqs.append({"addConditionalFormatRule":{"index":0,"rule":{"ranges":[rng],"booleanRule":{"condition":{"type":"CUSTOM_FORMULA","values":[{"userEnteredValue":'=AND(D$7="%";ISNUMBER(D8);D8>=0,995)'}]},"format":{"backgroundColor":verde,"textFormat":{"bold":True,"foregroundColor":{"red":0,"green":0.38,"blue":0}}}}}}})
reqs.append({"addConditionalFormatRule":{"index":1,"rule":{"ranges":[rng],"booleanRule":{"condition":{"type":"CUSTOM_FORMULA","values":[{"userEnteredValue":'=AND(D$7="%";ISNUMBER(D8);D8>0)'}]},"format":{"backgroundColor":ama2,"textFormat":{"foregroundColor":{"red":0.6,"green":0.34,"blue":0}}}}}}})
batch(reqs)
time.sleep(10)
v=get('FOLLOWUP_OPERACOES!A5:Q26')
for r in v: print(r)
print('ERROS:',[ (i,x) for i,r in enumerate(get('FOLLOWUP_OPERACOES!A5:CZ30')) for x in r if isinstance(x,str) and x.startswith('#')][:10])
