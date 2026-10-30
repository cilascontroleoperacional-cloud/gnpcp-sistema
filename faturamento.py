"""
Parâmetros de faturamento a partir dos PDFs diários (Power BI da empresa).

Cada PDF traz uma linha de controle:
  27/10/2026 09:07:20;20/11/2026;GN1270;448366,55;2105201,2;23,84;4,84
  gerado_em ; fim_competência ; GN ; fat_total ; meta ; dias_úteis ; dias_trabalhados

Regras (definidas pelo usuário em 27/10/2026):
- O PDF é a referência. META (F), Dias Úteis (M) e Dias Trabalhados (N) de
  FATURAMENTO_COMPILADO são copiados do PDF, na linha GN + competência.
- FAT. TOTAL (D) continua com a SUMIFS sobre CDO_PRODUCAO; o fat. do PDF é só
  conferência. Divergência > R$ 0,05 => diagnóstico boletim a boletim contra o ProdControl.
- "Faturado em NF" (Q) não é usado.
"""
import io
import re
from datetime import datetime, timedelta

import requests

SHEET_ID = "1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4"   # GNPCP_BASE_2026
ABA_FAT = "FATURAMENTO_COMPILADO"
LINHA_CAB_FAT = 7            # cabeçalho; dados a partir da linha 8
TOLERANCIA = 0.05            # R$

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

CR_CONTRATO = {   # CR -> contractId no ProdControl
    "GN1270": "5a5763bf-e84c-4027-831e-9f2c5e4a4f76",   # LACAN
    "GN1400": "20f59d50-b39a-4140-9aa7-6efcef3b05c5",   # ARAUCO
    "GN1410": "bbff595d-2b32-4f35-8c43-20f9e944a46e",   # MS Florestal / BRACELL
    "GN1420": "f11ab962-3a16-42ed-88e9-7604d6ccde19",   # Innovatech
    "GN1421": "49383261-b78c-4603-94d2-fb48064346f1",   # COLPAR
    "GN1430": "390ec113-d920-4f77-a260-eef7537cd7b7",   # Eucatex
}

RE_LINHA = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s*(\d{2}:\d{2}:\d{2});(\d{2}/\d{2}/\d{4});(GN\d{4});"
    r"([\d.,]+);([\d.,]+);([\d.,]+);([\d.,]+)")

# Cartão visível do PDF ("23,51 Dias Úteis", "6,51 Dias Trabalhados"). A linha de controle
# às vezes vem CORTADA pelo Power BI ("...;23,51;6,…"), então os dias saem do cartão.
RE_DIAS_UTEIS = re.compile(r"(\d+(?:,\d+)?)\s*Dias\s*Úteis", re.I)
RE_DIAS_TRAB = re.compile(r"(\d+(?:,\d+)?)\s*Dias\s*Trabalhados", re.I)


def _br(s):
    """'1.234,56' / '1234,56' / '23' -> float"""
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def label_competencia(fim_ddmmaaaa):
    """'20/11/2026' -> 'Novembro-26' (competência termina no dia 20 do mês dela)."""
    d = datetime.strptime(fim_ddmmaaaa, "%d/%m/%Y")
    return f"{MESES[d.month - 1]}-{str(d.year)[2:]}"


def ordem_competencia(label):
    """'Novembro-26' -> (2026, 11); desconhecido -> (0, 0)."""
    try:
        mes, aa = str(label).strip().rsplit("-", 1)
        return (2000 + int(aa), MESES.index(mes.strip().capitalize()) + 1)
    except (ValueError, IndexError):
        return (0, 0)


def janela_competencia(fim_ddmmaaaa):
    """Competência = 21 do mês anterior até o dia 20 do mês dela."""
    fim = datetime.strptime(fim_ddmmaaaa, "%d/%m/%Y")
    ini = (fim.replace(day=1) - timedelta(days=1)).replace(day=21)
    return ini.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")


# ---------------------------------------------------------------- PDF
def ler_pdf(conteudo: bytes, nome=""):
    """Extrai a linha de controle do PDF. Retorna dict ou levanta ValueError."""
    from pypdf import PdfReader
    try:
        rd = PdfReader(io.BytesIO(conteudo))
        bruto = "".join((p.extract_text() or "") + "\n" for p in rd.pages[:3])
    except Exception:
        raise ValueError(f"{nome}: não é um PDF válido ou o arquivo está corrompido")
    plano = re.sub(r"\s+", " ", bruto).replace("; ", ";").replace(" ;", ";")
    m = RE_LINHA.search(plano)
    if not m:
        raise ValueError(f"{nome}: linha de controle não encontrada no PDF")
    gerado_d, gerado_h, fim, gn, fat, meta, uteis, trab = m.groups()
    cortada = plano[m.end():m.end() + 1] in ("…", ".") or trab.endswith((",", "."))
    vis_u, vis_t = RE_DIAS_UTEIS.search(plano), RE_DIAS_TRAB.search(plano)
    if vis_u:
        uteis = vis_u.group(1)
    if vis_t:
        trab = vis_t.group(1)
    elif cortada:
        raise ValueError(f"{nome}: Dias Trabalhados cortado no PDF e não achado no cartão — confira o arquivo")
    return {
        "arquivo": nome,
        "responsavel": ler_responsavel(conteudo),
        "gerado_em": f"{gerado_d} {gerado_h}",
        "fim_competencia": fim,
        "competencia": label_competencia(fim),
        "gn": gn,
        "fat_pdf": round(_br(fat), 2),
        "meta": round(_br(meta), 2),
        "dias_uteis": round(_br(uteis), 2),
        "dias_trabalhados": round(_br(trab), 2),
    }


def ler_texto(texto: str, nome=""):
    """
    Mesma leitura de ler_pdf(), mas a partir do TEXTO das 3 primeiras páginas, extraído no
    navegador (pdf.js) — o app envia ~1 KB em vez de MBs de PDF. Páginas separadas por '\f'.
    """
    plano = re.sub(r"\s+", " ", texto).replace("; ", ";").replace(" ;", ";")
    m = RE_LINHA.search(plano)
    if not m:
        raise ValueError(f"{nome}: linha de controle não encontrada no texto do PDF")
    gerado_d, gerado_h, fim, gn, fat, meta, uteis, trab = m.groups()
    cortada = plano[m.end():m.end() + 1] in ("…", ".") or trab.endswith((",", "."))
    vis_u, vis_t = RE_DIAS_UTEIS.search(plano), RE_DIAS_TRAB.search(plano)
    if vis_u:
        uteis = vis_u.group(1)
    if vis_t:
        trab = vis_t.group(1)
    elif cortada:
        raise ValueError(f"{nome}: Dias Trabalhados cortado no PDF e não achado no cartão — confira o arquivo")
    return {
        "arquivo": nome,
        "responsavel": _responsavel_do_texto(texto.split("\f")[0]),
        "gerado_em": f"{gerado_d} {gerado_h}",
        "fim_competencia": fim,
        "competencia": label_competencia(fim),
        "gn": gn,
        "fat_pdf": round(_br(fat), 2),
        "meta": round(_br(meta), 2),
        "dias_uteis": round(_br(uteis), 2),
        "dias_trabalhados": round(_br(trab), 2),
    }


def _responsavel_do_texto(pag1: str):
    """Página 1 vem como bloco de rótulos ('COMPETÊNCIA:', 'CONTRATO:', 'RESPONSÁVEL:') e depois os valores na mesma ordem."""
    linhas = [x.strip() for x in pag1.splitlines() if x.strip()]
    for i, x in enumerate(linhas):
        if x.upper().startswith("RESPONS") and x.endswith(":"):
            ini = i
            while ini > 0 and linhas[ini - 1].endswith(":"):
                ini -= 1
            fim = i
            while fim + 1 < len(linhas) and linhas[fim + 1].endswith(":"):
                fim += 1
            pos = i - ini
            valores = linhas[fim + 1:]
            if pos < len(valores):
                return re.sub(r"\s+", " ", valores[pos]).strip()
        if x.upper().startswith("RESPONS") and ":" in x and not x.endswith(":"):
            return x.split(":", 1)[1].strip()
    return ""


def ler_responsavel(conteudo: bytes):
    """
    Nome do responsável (cabeçalho 'RESPONSÁVEL:' da página 1) via pdftotext -layout
    (poppler). O pypdf quebra letras ('CARLOS M AGNO'), então sem pdftotext devolve "".
    """
    import subprocess
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(conteudo)
            tmp.flush()
            txt = subprocess.run(["pdftotext", "-layout", "-l", "1", tmp.name, "-"],
                                 capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return ""
    m = re.search(r"RESPONS[ÁA]VEL:\s*([^\n]+)", txt)
    if not m:
        return ""
    nome = re.split(r"\s{3,}", m.group(1).strip())[0].strip()
    return nome if re.fullmatch(r"[A-ZÀ-Ý][A-ZÀ-Ý .'-]{2,60}", nome) else ""


# ---------------------------------------------------------------- Sheets (REST)
class Planilha:
    def __init__(self, access_token, sheet_id=SHEET_ID):
        self.h = {"Authorization": f"Bearer {access_token}"}
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"

    def get(self, rng, render="UNFORMATTED_VALUE"):
        r = requests.get(f"{self.base}/values/{rng}", headers=self.h, timeout=120,
                         params={"valueRenderOption": render,
                                 "dateTimeRenderOption": "FORMATTED_STRING"})
        r.raise_for_status()
        return r.json().get("values", [])

    def batch_get(self, rngs, render="UNFORMATTED_VALUE"):
        r = requests.get(f"{self.base}/values:batchGet", headers=self.h, timeout=180,
                         params=[("ranges", x) for x in rngs] +
                                [("valueRenderOption", render),
                                 ("dateTimeRenderOption", "FORMATTED_STRING")])
        r.raise_for_status()
        return [vr.get("values", []) for vr in r.json()["valueRanges"]]

    def update(self, dados):
        """dados = [(range, [[...]]), ...] em USER_ENTERED — planilha pt-BR: fórmulas com ';'."""
        body = {"valueInputOption": "USER_ENTERED",
                "data": [{"range": rg, "values": v} for rg, v in dados]}
        r = requests.post(f"{self.base}/values:batchUpdate", headers=self.h,
                          json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    def sheet_id_num(self, titulo):
        r = requests.get(self.base, headers=self.h, timeout=60,
                         params={"fields": "sheets.properties(sheetId,title)"})
        r.raise_for_status()
        for s in r.json()["sheets"]:
            if s["properties"]["title"] == titulo:
                return s["properties"]["sheetId"]
        raise KeyError(titulo)

    def inserir_linha(self, titulo, linha_1based, copiar_formato_de_cima=True):
        sid = self.sheet_id_num(titulo)
        body = {"requests": [{"insertDimension": {
            "range": {"sheetId": sid, "dimension": "ROWS",
                      "startIndex": linha_1based - 1, "endIndex": linha_1based},
            "inheritFromBefore": copiar_formato_de_cima}}]}
        r = requests.post(f"{self.base}:batchUpdate", headers=self.h, json=body, timeout=60)
        r.raise_for_status()

    def log(self, rotina, resultado, detalhe):
        """Mesma convenção do Code.gs: entrada nova no topo da aba LOG (linha 2)."""
        from atualizar_base import Base, registrar_log
        registrar_log(Base(self.h["Authorization"].split(" ", 1)[1], self.base.rsplit("/", 1)[1]),
                      rotina, resultado, detalhe)


# ---------------------------------------------------------------- base
def soma_base(pl, gn, competencia):
    """
    Soma de CDO_PRODUCAO!AI (Valor Total) para CR + Competência, total e por boletim.
    Também devolve o mapa (operação, função) -> Tipo Recurso do CR (maioria no histórico),
    que diz qual linha do boletim carrega o valor (só 'Principal' fatura).
    """
    a, d, f, n_, ab, ag, ai = pl.batch_get([
        "CDO_PRODUCAO!A6:A", "CDO_PRODUCAO!D6:D", "CDO_PRODUCAO!F6:F", "CDO_PRODUCAO!N6:N",
        "CDO_PRODUCAO!AB6:AB", "CDO_PRODUCAO!AG6:AG", "CDO_PRODUCAO!AI6:AI"])
    n = max(len(a), len(d), len(ag), len(ai))
    cel = lambda col, i: (col[i][0] if i < len(col) and col[i] else "")
    total, por_bol, cont = 0.0, {}, {}
    for i in range(n):
        if cel(d, i) != gn:
            continue
        k = (str(cel(n_, i)).strip().upper(), str(cel(f, i)).strip().upper())
        tp = cel(ab, i)
        if tp:
            cont.setdefault(k, {}).setdefault(tp, 0)
            cont[k][tp] += 1
        if cel(ag, i) == competencia:
            try:
                v = float(cel(ai, i) or 0)
            except (TypeError, ValueError):
                v = 0.0
            total += v
            bol = str(cel(a, i)).split(".")[0]
            por_bol[bol] = por_bol.get(bol, 0.0) + v
    tipo = {k: max(c, key=c.get) for k, c in cont.items()}
    return round(total, 2), por_bol, tipo


def diagnosticar(api, gn, fim_competencia, base_por_bol, tipo, ate_iso=None):
    """
    Compara, boletim a boletim, o valor da base com o ProdControl
    (produção x preço vigente). Só a linha cuja função é 'Principal' na operação
    fatura (mesma regra de CDO_PRODUCAO!AI); a classificação vem do histórico da base.
    """
    ini, fim = janela_competencia(fim_competencia)
    if ate_iso:
        fim = min(fim, ate_iso)
    cid = CR_CONTRATO.get(gn)
    if not cid:
        return [{"erro": f"{gn} sem contractId mapeado"}]
    ids, page = [], 1
    while True:
        d = api.get(f"/odc?contractId={cid}&limit=255&page={page}")
        items = d.get("items", [])
        ids += [x for x in items if ini <= x.get("bulletinDate", "") <= fim]
        if not items or min(x.get("bulletinDate", "9") for x in items) < ini:
            break
        page += 1
    api_por_bol, detalhe = {}, {}
    for x in ids:
        det = api.get(f"/odc/{x['id']}")
        cod = str(det["code"])
        for p in det.get("operationDailyControlProductions", []):
            pf = p.get("priceFormation") or {}
            op = (pf.get("operation") or {}).get("name", "")
            func = (p.get("resourceType") or {}).get("name", "")
            if tipo.get((op.strip().upper(), func.strip().upper())) != "Principal":
                continue
            preco = float(pf.get("totalPrice") or 0)
            qtd = float(p.get("productiveAmount") or 0)
            api_por_bol[cod] = api_por_bol.get(cod, 0.0) + qtd * preco
            detalhe.setdefault(cod, []).append(
                {"data": det.get("bulletinDate"), "operacao": op, "funcao": func,
                 "talhao": (p.get("plot") or {}).get("name"), "qtd": qtd, "preco": preco})
    difs = []
    for cod in sorted(set(api_por_bol) | set(base_por_bol)):
        va, vb = round(api_por_bol.get(cod, 0), 2), round(base_por_bol.get(cod, 0), 2)
        if abs(va - vb) > TOLERANCIA:
            difs.append({"boletim": cod, "prodcontrol": va, "base": vb,
                         "diferenca": round(vb - va, 2),
                         "itens_prodcontrol": detalhe.get(cod, []),
                         "causa_provavel": ("boletim ausente na base" if vb == 0 else
                                            "boletim não existe mais no ProdControl" if va == 0 else
                                            "preço ou quantidade diferente")})
    return difs


# ---------------------------------------------------------------- gravação
FORMULAS_LINHA = {   # colunas com fórmula numa linha nova (padrão das linhas 18-21)
    "D": "=SUMIFS(CDO_PRODUCAO!$AI:$AI;CDO_PRODUCAO!$AG:$AG;FATURAMENTO_COMPILADO!$P{r};CDO_PRODUCAO!$D:$D;A{r})",
    "E": "=(D{r}/N{r})*M{r}",
    "G": '=IFERROR(D{r}/F{r};"")',
    "H": "=IF(F{r}-D{r}<0;0;F{r}-D{r})",
    "I": "=D{r}/N{r}",
    "J": '=IFERROR(E{r}/F{r};"")',
    "K": "=IFERROR(IF(H{r}/O{r}<0;0;H{r}/O{r});0)",
    "L": "=(F{r}/M{r})*N{r}",
    "O": "=M{r}-N{r}",
    "R": '=IF(Q{r}=0;"";Q{r}-D{r})',
    "S": '=IF(R{r}="";"";R{r}/D{r})',
}


def ler_fat(pl):
    v = pl.get(f"{ABA_FAT}!A{LINHA_CAB_FAT + 1}:S200", render="FORMULA")
    linhas = []
    for i, r in enumerate(v):
        r = list(r) + [""] * (19 - len(r))
        linhas.append({"linha": LINHA_CAB_FAT + 1 + i, "gn": str(r[0]).strip(),
                       "resp": r[1], "contrato": r[2], "comp": str(r[15]).strip(),
                       "D": r[3], "F": r[5], "M": r[12], "N": r[13]})
    return linhas


def planejar(pl, params):
    """Decide, para cada PDF, se atualiza uma linha existente ou cria uma nova."""
    linhas = ler_fat(pl)
    dados = [x for x in linhas if re.match(r"^GN\d{4}$", x["gn"])]
    total = next((x for x in linhas if str(x["D"]).upper().startswith("=SUBTOTAL")), None)
    plano = []
    for p in params:
        alvo = next((x for x in dados if x["gn"] == p["gn"] and x["comp"] == p["competencia"]), None)
        do_gn = [x for x in dados if x["gn"] == p["gn"]]
        modelo = max(do_gn, key=lambda x: ordem_competencia(x["comp"])) if do_gn else None
        item = dict(p)
        if alvo:
            item["acao"] = "atualizar"
            item["linha"] = alvo["linha"]
            item["antes"] = {"B": alvo["resp"], "F": alvo["F"], "M": alvo["M"], "N": alvo["N"]}
        else:
            item["acao"] = "criar"
            item["linha"] = None
            if not modelo:
                raise ValueError(f"{p['gn']} não tem nenhuma linha em {ABA_FAT} para servir de modelo")
            item["contrato"] = modelo["contrato"]
            item["responsavel"] = p.get("responsavel") or modelo["resp"]
        plano.append(item)
    return plano, total


def gravar(pl, plano, linha_total):
    """Aplica o plano. Linhas novas entram logo acima da linha de total."""
    upd = []
    for it in [x for x in plano if x["acao"] == "atualizar"]:
        r = it["linha"]
        resp = (it.get("responsavel") or "").strip()
        if resp and resp != str(it["antes"]["B"]):
            upd.append((f"{ABA_FAT}!B{r}", [["'" + resp]]))
        upd += [(f"{ABA_FAT}!F{r}", [[it["meta"]]]),
                (f"{ABA_FAT}!M{r}:N{r}", [[it["dias_uteis"], it["dias_trabalhados"]]])]
    if upd:
        pl.update(upd)

    novas = [x for x in plano if x["acao"] == "criar"]
    if novas:
        if not linha_total:
            raise RuntimeError("Linha de SUBTOTAL não encontrada em FATURAMENTO_COMPILADO")
        tot = linha_total["linha"]
        for it in novas:
            pl.inserir_linha(ABA_FAT, tot)          # nova linha ocupa a posição 'tot'
            r = tot
            linha = {c: f.format(r=r) for c, f in FORMULAS_LINHA.items()}
            linha.update({"A": it["gn"], "B": "'" + str(it["responsavel"]), "C": "'" + str(it["contrato"]),
                          "F": it["meta"], "M": it["dias_uteis"], "N": it["dias_trabalhados"],
                          "P": "'" + it["competencia"], "Q": ""})   # apóstrofo: força TEXTO (senão vira data)
            vals = [[linha.get(chr(ord("A") + i), "") for i in range(19)]]
            pl.update([(f"{ABA_FAT}!A{r}:S{r}", vals)])
            it["linha"] = r
            tot += 1
        # SUBTOTAIS passam a cobrir até a última linha de dados
        ult = tot - 1
        pl.update([(f"{ABA_FAT}!D{tot}", [[f"=SUBTOTAL(109;D{LINHA_CAB_FAT + 1}:D{ult})"]]),
                   (f"{ABA_FAT}!F{tot}", [[f"=SUBTOTAL(109;F{LINHA_CAB_FAT + 1}:F{ult})"]])])
    return plano
