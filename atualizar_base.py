"""
Atualização da GNPCP_BASE_2026 (CDO_MAQUINAS / CDO_PRODUCAO) direto da API do ProdControl.

Fontes na API (todas filtram no servidor por contractId + startDate/endDate):
  /odc             cabeçalho do boletim (código, data, CR, turma, supervisor, encarregado...)
  /odc/machine     linhas de máquina, com paralisações (tipo), tipo do recurso e unidade
  /odc/production  linhas de produção, com a composição da formação de preço
                   (typeHasPricesFormation: Principal/Apoio/Suporte, preço e rendimento por função)

Regras espelhadas do Code.gs (consolidarMaquinas / consolidarProducao):
  - CDO_MAQUINAS: por máquina, 1 linha por paralisação + 1 linha TRABALHADA
  - CDO_PRODUCAO: 1 linha por linha de produção
  - boletim (CDO + CR) já existente é SUBSTITUÍDO, nunca duplicado
  - fórmulas copiadas de uma linha viva da própria planilha (copyPaste) — seguem a fórmula
    que estiver valendo, mesmo que o Code.gs do projeto esteja desatualizado
  - colunas técnicas: Chave, Importado_Em, Fonte

Diferença em relação ao Code.gs: só regrava boletins NOVOS ou ALTERADOS (comparação célula a
célula das colunas de origem). Tudo é aplicado num único spreadsheets.batchUpdate (atômico).
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date
from urllib.parse import urlencode

import requests

SHEET_ID = "1vI98vypQs8BJOmMTVuDf6Bk0kTJ2GjHMaYT-syxIDB4"   # GNPCP_BASE_2026

COLS_MAQ_ORIGEM = [
    "CDO", "Data", "Semana", "CR", "Contrato", "Cod. Maquina", "Descricao", "Recurso",
    "Escala de Horas", "Mat. Supervisor", "Supervisor", "Mat. Encarregado", "Encarregado", "Turma",
    "Cod. Operacao", "Operacao", "Und. Medida", "Projeto", "Nome Projeto", "Talhao", "Mat. Operador",
    "Operador", "Cod Paralização", "Tipo Paralização", "Paralização", "Horas", "Producao",
    "Rendimento Previsto", "Rendimento Efetivo", "Rendimento Total", "Horimetro Inicial",
    "Horimetro Final", "Tipo de Recurso", "Preço do Recurso", "Criado por", "Alterado por",
    "Data Registro", "Obs"]
COLS_PROD_ORIGEM = [
    "CDO", "Data", "Comp/Semana", "CR", "Contrato", "Funcao", "Escala de Horas",
    "Mat. Supervisor", "Supervisor", "Mat. Encarregado", "Encarregado", "Turma", "Cod. Operacao",
    "Operacao", "Und. Medida", "Cod. Projeto", "Projeto", "Talhao", "Hora Trabalhada", "Producao",
    "Hora Improdutiva", "Total Horas", "Rendimento Previsto", "Rendimento Efetivo", "Rendimento Total",
    "Preço do Recurso", "Status", "Tipo Recurso", "Criado por", "Alterado por", "Data Registro",
    "Observacao"]
COLS_TEC = ["Chave", "Importado_Em", "Fonte"]

# Colunas fora da comparação (o valor da base é mantido se todo o resto for igual):
#  - Rendimento Total de máquinas: a exportação do ProdControl usa uma regra inconsistente quando
#    trator e implemento dividem as mesmas paradas (3 de 1.028 linhas em 21-26/10/2026). A coluna não
#    é usada por fórmulas nem dashboards. Boletins novos/alterados recebem (horas + paradas) / produção.
ABAS = {
    "MAQ": {"nome": "CDO_MAQUINAS", "cab": 8, "origem": COLS_MAQ_ORIGEM, "comp": "Competência2",
            "ignorar": ["Rendimento Total"]},
    "PROD": {"nome": "CDO_PRODUCAO", "cab": 5, "origem": COLS_PROD_ORIGEM, "comp": "Competência",
             "ignorar": []},
}

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
EPOCA = date(1899, 12, 30)                    # data zero das planilhas
FUSO_REGISTRO = timedelta(hours=-3)           # ProdControl registra em horário de Brasília (conferido com a base)


# =============================================================== utilitários
def serial_data(d):
    return (d - EPOCA).days


def serial_dt(iso):
    """'2026-10-27T14:08:23.879Z' -> número de série da planilha no fuso local."""
    if not iso:
        return ""
    dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S") + FUSO_REGISTRO
    base = datetime(1899, 12, 30)
    return (dt - base).total_seconds() / 86400.0


def num(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default


def limpo(x):
    """8.0 -> 8 ; 0.4700 -> 0.47 (como a planilha mostra o valor colado)."""
    x = round(float(x), 6)
    return int(x) if x == int(x) else x


def cod(v):
    """Como a planilha converte o texto colado: só dígitos vira número ('02' -> 2)."""
    s = "" if v is None else str(v).strip()
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d+\.\d+", s):
        return limpo(float(s))
    return s


def r2(x):
    """Arredondamento comercial (0,365 -> 0,37), igual à planilha — round() do Python daria 0,36."""
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def rend(horas, prod):
    return limpo(r2(horas / prod)) if prod else 0


def competencia_label(d):
    m, y = d.month, d.year
    if d.day >= 21:
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return f"{MESES[m - 1]}-{str(y)[2:]}"


def inicio_competencia(d):
    if d.day >= 21:
        return date(d.year, d.month, 21)
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(y, m, 21)


def semana(d):
    """Espelho de semana() do Code.gs: 'n°- MM/AAAA'."""
    ini = inicio_competencia(d)
    dom, x = 0, ini + timedelta(days=1)
    while x <= d:
        if x.weekday() == 6:
            dom += 1
        x += timedelta(days=1)
    m, y = ini.month + 1, ini.year
    if m > 12:
        m, y = 1, y + 1
    return f"{dom + 1}°- {m:02d}/{y}"


def txt(v):
    """Espelho de txt() do Code.gs (para montar a Chave)."""
    if v is None or v == "":
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def chave_maq(r):
    return "|".join(txt(r[c]) for c in ["CDO", "Cod. Maquina", "Cod Paralização", "Cod. Operacao",
                                        "Projeto", "Talhao", "Mat. Operador"]) + "|" + txt(r["Horas"])


def chave_prod(r):
    return ("|".join(txt(r[c]) for c in ["CDO", "Funcao", "Encarregado", "Cod. Operacao",
                                         "Cod. Projeto", "Talhao", "Tipo Recurso"]) + "|" +
            "|".join(txt(r[c]) for c in ["Hora Trabalhada", "Producao", "Hora Improdutiva"]))


# =============================================================== coleta na API
def paginar(api, path, params, limite=255):
    out, page = [], 1
    while True:
        q = dict(params, limit=limite, page=page)
        d = api.get(f"{path}?{urlencode(q)}")
        out += d.get("items", [])
        if page >= (d.get("meta") or {}).get("totalPages", 1):
            return out
        page += 1


def coletar(api, contratos, ini_iso, fim_iso, log=print):
    """Baixa cabeçalhos, máquinas e produção da janela. Lança erro se qualquer contrato falhar
    (assim nunca se compara/apaga com dados incompletos)."""
    dados = {"odc": [], "maq": [], "prod": []}
    for c in contratos:
        p = {"contractId": c["contractId"], "startDate": ini_iso, "endDate": fim_iso}
        cab = paginar(api, "/odc", p)
        maq = paginar(api, "/odc/machine", p)
        prod = paginar(api, "/odc/production", p)
        for x in cab:
            x["_contrato_nome"] = c["nome"]
        dados["odc"] += cab
        dados["maq"] += maq
        dados["prod"] += prod
        log(f"  {c['nome']}: {len(cab)} boletins | {len(maq)} máquinas | {len(prod)} produções")
    return dados


class Ativos:
    """Descrição (fabricante - modelo) dos patrimônios, 1 chamada por máquina distinta."""

    def __init__(self, api):
        self.api, self.cache = api, {}

    def carregar(self, ids, workers=4):
        novos = [i for i in set(ids) if i and i not in self.cache]

        def um(aid):
            try:
                a = self.api.get(f"/assets/{aid}")
            except Exception:
                return aid, ""
            fab = (a.get("manufacturer") or {}).get("name", "") or ""
            mod = (a.get("model") or {}).get("description", "") or (a.get("model") or {}).get("name", "") or ""
            return aid, (f"{fab} - {mod}" if fab and mod else (fab or mod))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for aid, desc in ex.map(um, novos):
                self.cache[aid] = desc

    def descricao(self, aid):
        return self.cache.get(aid, "")


def composicao(pf, resource_type_id):
    """Entrada da formação de preço para a função/recurso: (Tipo, Preço, Rendimento previsto)."""
    for t in pf.get("typeHasPricesFormation") or []:
        if (t.get("resourceType") or {}).get("id") == resource_type_id:
            return ((t.get("charge") or {}).get("name", "") or "",
                    limpo(r2(num(t.get("price")))), limpo(r2(num(t.get("income")))))
    return None


class Cadastro:
    """GET por id com cache (turmas -> CR; funcionários -> matrícula). 1 chamada por id distinto."""

    def __init__(self, api, caminho):
        self.api, self.caminho, self.cache = api, caminho, {}

    def carregar(self, ids, workers=4):
        novos = [i for i in set(ids) if i and i not in self.cache]

        def um(i):
            try:
                return i, self.api.get(f"{self.caminho}/{i}")
            except Exception:
                return i, {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, v in ex.map(um, novos):
                self.cache[i] = v

    def __getitem__(self, i):
        return self.cache.get(i) or {}


# =============================================================== montagem das linhas
def cabecalhos(odcs, turmas, pessoas):
    """id do boletim -> campos comuns às linhas (máquina e produção)."""
    out = {}
    for d in odcs:
        cls = turmas[(d.get("class") or {}).get("id")] or (d.get("class") or {})
        cc = cls.get("costCenter") or {}
        sup = pessoas[(d.get("supervisor") or {}).get("id")] or (d.get("supervisor") or {})
        lid = pessoas[(d.get("leader") or {}).get("id")] or (d.get("leader") or {})
        dt = datetime.strptime(d["bulletinDate"][:10], "%Y-%m-%d").date()
        out[d["id"]] = {
            "_data": dt, "_contrato": d.get("_contrato_nome", ""),
            "CDO": d["code"], "Data": serial_data(dt), "Semana": semana(dt), "Comp/Semana": semana(dt),
            "CR": cc.get("name", "") or "",
            "Contrato": (d.get("contract") or {}).get("description", "") or "",
            "Escala de Horas": limpo(num(d.get("hourScale"))),
            "Mat. Supervisor": cod(sup.get("employeeNumber")), "Supervisor": sup.get("name", "") or "",
            "Mat. Encarregado": cod(lid.get("employeeNumber")), "Encarregado": lid.get("name", "") or "",
            "Turma": cls.get("name", "") or "",
            "_criado": (d.get("createdBy") or {}).get("name", "") or "",
            "_alterado": (d.get("updatedBy") or {}).get("name", "") or "",
            "_obs": d.get("observation", "") or "",
        }
    return out


def linhas_maquinas(dados, cab, ativos, pfs, avisos):
    saida = []
    for m in dados["maq"]:
        h = cab.get((m.get("operationDailyControl") or {}).get("id"))
        if not h:
            avisos.add(f"máquina sem cabeçalho de boletim (id {m.get('id')})")
            continue
        asset = m.get("asset") or {}
        rtipo = asset.get("resourceType") or {}
        pf = m.get("priceFormation") or {}
        op = pf.get("operation") or {}
        emp, proj, plot = m.get("employee") or {}, m.get("project") or {}, m.get("plot") or {}
        comp = composicao(pfs.get(pf.get("id"), {}), rtipo.get("id"))
        if comp is None:
            avisos.add(f"sem formação de preço para máquina: {h['CR']} | {op.get('code')} | {rtipo.get('name')}")
            comp = ("", 0, 0)
        tipo, preco, rprev = comp
        base = {c: h.get(c, "") for c in COLS_MAQ_ORIGEM}
        base.update({
            "Cod. Maquina": asset.get("code", "") or "", "Descricao": ativos.descricao(asset.get("id")),
            "Recurso": rtipo.get("name", "") or "",
            "Cod. Operacao": cod(op.get("code")), "Operacao": op.get("name", "") or "",
            "Und. Medida": (op.get("measureUnit") or {}).get("symbol", "") or "",
            "Projeto": cod(proj.get("code")), "Nome Projeto": proj.get("name", "") or "",
            "Talhao": cod(plot.get("name")),
            "Mat. Operador": cod(emp.get("employeeNumber")), "Operador": emp.get("name", "") or "",
            "Horimetro Inicial": limpo(num(m.get("hourMeterStart"))),
            "Horimetro Final": limpo(num(m.get("hourMeterEnd"))),
            "Tipo de Recurso": tipo, "Preço do Recurso": preco,
            "Criado por": (m.get("createdBy") or {}).get("name", "") or "",
            "Alterado por": (m.get("updatedBy") or {}).get("name", "") or "",   # vazio = nunca alterada
            "Data Registro": serial_dt(m.get("createdAt")), "Obs": h["_obs"],
        })
        paradas = 0.0
        for s in m.get("odcMachineStoppages") or []:
            ws = s.get("workStoppage") or {}
            r = dict(base)
            r.update({"Cod Paralização": cod(ws.get("code")),
                      "Tipo Paralização": (ws.get("type") or {}).get("name", "") or "",
                      "Paralização": ws.get("description", "") or "",
                      "Horas": limpo(num(s.get("time"))), "Producao": "",
                      "Rendimento Previsto": "", "Rendimento Efetivo": "", "Rendimento Total": ""})
            paradas += num(s.get("time"))
            saida.append(r)
        horas, prod = num(m.get("workedHours")), num(m.get("productiveAmount"))
        r = dict(base)
        r.update({"Cod Paralização": "TRABALHADA", "Tipo Paralização": "TRABALHADA",
                  "Paralização": "TRABALHADA", "Horas": limpo(horas), "Producao": limpo(prod),
                  "Rendimento Previsto": rprev, "Rendimento Efetivo": rend(horas, prod),
                  "Rendimento Total": rend(horas + paradas, prod)})
        saida.append(r)
    return saida


def linhas_producao(dados, cab, pfs, avisos):
    saida = []
    for p in dados["prod"]:
        h = cab.get((p.get("operationDailyControl") or {}).get("id"))
        if not h:
            avisos.add(f"produção sem cabeçalho de boletim (id {p.get('id')})")
            continue
        pf = p.get("priceFormation") or {}
        op = pf.get("operation") or {}
        rtipo = p.get("resourceType") or {}
        proj, plot = p.get("project") or {}, p.get("plot") or {}
        comp = composicao(pfs.get(pf.get("id")) or pf, rtipo.get("id"))
        if comp is None:
            avisos.add(f"sem formação de preço para função: {h['CR']} | {op.get('code')} | {rtipo.get('name')}")
            comp = ("", 0, 0)
        tipo, preco, rprev = comp
        ht, hi, prod = num(p.get("workedHours")), num(p.get("unproductiveHours")), num(p.get("productiveAmount"))
        r = {c: h.get(c, "") for c in COLS_PROD_ORIGEM}
        r.update({
            "Funcao": rtipo.get("name", "") or "",
            "Cod. Operacao": cod(op.get("code")), "Operacao": op.get("name", "") or "",
            "Und. Medida": (op.get("measureUnit") or {}).get("symbol", "") or "",
            "Cod. Projeto": cod(proj.get("code")), "Projeto": proj.get("name", "") or "",
            "Talhao": cod(plot.get("name")),
            "Hora Trabalhada": limpo(ht), "Producao": limpo(prod), "Hora Improdutiva": limpo(hi),
            "Total Horas": limpo(ht + hi), "Rendimento Previsto": rprev,
            "Rendimento Efetivo": rend(ht, prod), "Rendimento Total": rend(ht + hi, prod),
            "Preço do Recurso": preco, "Status": status_producao(p), "Tipo Recurso": tipo,
            "Criado por": (p.get("createdBy") or {}).get("name", "") or "",
            "Alterado por": (p.get("updatedBy") or {}).get("name", "") or "",
            "Data Registro": serial_dt(p.get("createdAt")), "Observacao": h["_obs"],
        })
        saida.append(r)
    return saida


def status_producao(p):
    return (p.get("status") or {}).get("name", "") or ""


# =============================================================== planilha (REST)
class Base:
    def __init__(self, access_token, sheet_id=SHEET_ID):
        self.h = {"Authorization": f"Bearer {access_token}"}
        self.url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"

    def _req(self, metodo, path, **kw):
        for t in range(4):
            r = requests.request(metodo, self.url + path, headers=self.h, timeout=300, **kw)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(5 * (t + 1))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()

    def valores(self, rngs, render="UNFORMATTED_VALUE"):
        q = [("ranges", x) for x in rngs] + [("valueRenderOption", render),
                                             ("dateTimeRenderOption", "SERIAL_NUMBER")]
        return [vr.get("values", []) for vr in self._req("GET", "/values:batchGet", params=q)["valueRanges"]]

    def meta(self):
        return self._req("GET", "", params={
            "fields": "sheets(properties(sheetId,title,gridProperties),basicFilter)"})

    def batch(self, requests_):
        return self._req("POST", ":batchUpdate", json={"requests": requests_})


def col_letra(n):          # 1 -> A
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _norm(v):
    """Valor comparável (planilha x API)."""
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    s = str(v).strip()
    return s


def _norm_linha(r, cols, i_reg, ignorar=()):
    out = []
    for j, c in enumerate(cols):
        v = r[j] if j < len(r) else ""
        if c in ignorar:
            v = ""
        elif j == i_reg:                         # Data Registro: compara até o segundo
            v = round(float(v) * 86400) if isinstance(v, (int, float)) else _norm(v)
        else:
            v = _norm(v)
        out.append(v)
    return tuple(out)


def ler_aba(base, cfg):
    """Lê cabeçalho, CDO/CR de todas as linhas e posição das colunas técnicas."""
    nome, h = cfg["nome"], cfg["cab"]
    cab = base.valores([f"{nome}!A{h}:ZZ{h}"])[0][0]
    n = len(cfg["origem"])
    if [str(x).strip() for x in cab[:n]] != cfg["origem"]:
        raise RuntimeError(f"{nome}: colunas A..{col_letra(n)} diferentes do esperado — nada foi gravado")
    i_tec = cab.index("Chave")
    if cab[i_tec:i_tec + 3] != COLS_TEC:
        raise RuntimeError(f"{nome}: colunas técnicas fora do lugar")
    a, d = base.valores([f"{nome}!A{h + 1}:A", f"{nome}!D{h + 1}:D"])
    total = max(len(a), len(d))
    cel = lambda col, i: (col[i][0] if i < len(col) and col[i] else "")
    chaves = [(txt(cel(a, i)), txt(cel(d, i))) for i in range(total)]
    return {"cab": cab, "i_tec": i_tec, "i_form": n, "n_form": i_tec - n,
            "chaves": chaves, "ultima": h + total}        # ultima = nº da última linha com dados


def comparar(base, cfg, info, novas):
    """
    Agrupa as linhas novas por (CDO, CR) e compara com a base.
    Retorna {'gravar': [linhas], 'apagar': [nº de linha], 'novos', 'alterados', 'iguais'}.
    """
    nome, h, cols = cfg["nome"], cfg["cab"], cfg["origem"]
    i_reg = cols.index("Data Registro")
    por_bol = {}
    for r in novas:
        por_bol.setdefault((txt(r["CDO"]), txt(r["CR"])), []).append(r)
    linhas_base = {}
    for i, k in enumerate(info["chaves"]):
        if k in por_bol:
            linhas_base.setdefault(k, []).append(h + 1 + i)
    vals = {}
    if linhas_base:
        ini = min(min(v) for v in linhas_base.values())
        bloco = base.valores([f"{nome}!A{ini}:{col_letra(len(cols))}{info['ultima']}"])[0]
        for k, rows in linhas_base.items():
            vals[k] = sorted((_norm_linha(bloco[x - ini] if x - ini < len(bloco) else [], cols, i_reg,
                                          cfg["ignorar"]) for x in rows), key=repr)
    res = {"gravar": [], "apagar": [], "novos": 0, "alterados": 0, "iguais": 0, "detalhe": []}
    for k, rs in por_bol.items():
        api = sorted((_norm_linha([r[c] for c in cols], cols, i_reg, cfg["ignorar"]) for r in rs), key=repr)
        if k not in linhas_base:
            res["novos"] += 1
        elif api == vals[k]:
            res["iguais"] += 1
            continue
        else:
            res["alterados"] += 1
            res["detalhe"].append(diferencas(k, vals[k], api, cols))
            res["apagar"] += linhas_base[k]
        res["gravar"] += rs
    res["gravar"].sort(key=lambda r: (r["Data"], r["CDO"]))
    return res


def diferencas(k, antes, depois, cols, maximo=3):
    """Resumo legível do que mudou num boletim (para o relatório)."""
    a, d = list(antes), list(depois)
    for x in list(a):
        if x in d:
            a.remove(x)
            d.remove(x)
    campos = set()
    for x, y in zip(a, d):
        campos |= {cols[j] for j in range(len(cols)) if x[j] != y[j]}
    return {"boletim": k[0], "cr": k[1], "linhas_antes": len(antes), "linhas_depois": len(depois),
            "campos": sorted(campos)[:10], "exemplo_antes": a[:1], "exemplo_depois": d[:1]}


def _celula(v):
    if v is None or v == "":
        return {}
    if isinstance(v, bool):
        return {"userEnteredValue": {"boolValue": v}}
    if isinstance(v, (int, float)):
        return {"userEnteredValue": {"numberValue": v}}
    return {"userEnteredValue": {"stringValue": str(v)}}


def _linha_modelo(base, cfg, info):
    """Última linha com fórmula viva na 1ª coluna calculada (fonte do copyPaste das fórmulas)."""
    nome, c0 = cfg["nome"], col_letra(info["i_form"] + 1)
    ult = info["ultima"]
    for ini in range(ult, cfg["cab"], -200):
        fim, comeco = ini, max(cfg["cab"] + 1, ini - 199)
        f = base.valores([f"{nome}!{c0}{comeco}:{c0}{fim}"], render="FORMULA")[0]
        for i in range(len(f) - 1, -1, -1):
            if f[i] and str(f[i][0]).startswith("="):
                return comeco + i
    raise RuntimeError(f"{nome}: nenhuma linha com fórmula viva para servir de modelo")


def montar_requests(base, cfg, info, plano, sheet_id, filtro, agora_serial, fonte):
    """Requests (na ordem certa) para anexar as linhas novas e apagar as versões antigas."""
    novas, apagar = plano["gravar"], sorted(set(plano["apagar"]))
    if not novas and not apagar:
        return [], info["ultima"]
    cols, n = cfg["origem"], len(novas)
    ult = info["ultima"]
    reqs = []
    if n:
        modelo = _linha_modelo(base, cfg, info)
        reqs.append({"insertDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                                   "startIndex": ult, "endIndex": ult + n},
                                         "inheritFromBefore": True}})
        reqs.append({"updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": ult, "columnIndex": 0},
            "rows": [{"values": [_celula(r[c]) for c in cols]} for r in novas],
            "fields": "userEnteredValue"}})
        tec = [[chave(cfg, r), agora_serial, fonte] for r in novas]
        reqs.append({"updateCells": {
            "start": {"sheetId": sheet_id, "rowIndex": ult, "columnIndex": info["i_tec"]},
            "rows": [{"values": [_celula(v) for v in t]} for t in tec],
            "fields": "userEnteredValue"}})
        reqs.append({"copyPaste": {
            "source": {"sheetId": sheet_id, "startRowIndex": modelo - 1, "endRowIndex": modelo,
                       "startColumnIndex": info["i_form"], "endColumnIndex": info["i_tec"]},
            "destination": {"sheetId": sheet_id, "startRowIndex": ult, "endRowIndex": ult + n,
                            "startColumnIndex": info["i_form"], "endColumnIndex": info["i_tec"]},
            "pasteType": "PASTE_FORMULA"}})
    # versões antigas: blocos contíguos, de baixo para cima (índices não se deslocam)
    blocos = []
    for x in apagar:
        if blocos and x == blocos[-1][1] + 1:
            blocos[-1][1] = x
        else:
            blocos.append([x, x])
    for a, b in reversed(blocos):
        reqs.append({"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                                   "startIndex": a - 1, "endIndex": b}}})
    nova_ult = ult + n - len(apagar)
    if filtro:
        f = dict(filtro)
        rg = dict(f["range"])
        rg["endRowIndex"] = nova_ult
        f["range"] = rg
        reqs.append({"setBasicFilter": {"filter": f}})
    return reqs, nova_ult


def chave(cfg, r):
    return chave_maq(r) if cfg["nome"] == "CDO_MAQUINAS" else chave_prod(r)


# =============================================================== LOG e orquestração
def agora_ms():
    return datetime.utcnow() + FUSO_REGISTRO


def registrar_log(base, rotina, resultado, detalhe):
    """Igual ao log_() do Code.gs: linha nova no topo da aba LOG (linha 2)."""
    sid = next(s["properties"]["sheetId"] for s in base.meta()["sheets"]
               if s["properties"]["title"] == "LOG")
    dt = agora_ms()
    serial = (dt - datetime(1899, 12, 30)).total_seconds() / 86400.0
    base.batch([
        {"insertDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 1, "endIndex": 2},
                             "inheritFromBefore": False}},
        {"updateCells": {"start": {"sheetId": sid, "rowIndex": 1, "columnIndex": 0},
                         "rows": [{"values": [_celula(serial), _celula(rotina), _celula(resultado),
                                              _celula(str(detalhe)[:45000])]}],
                         "fields": "userEnteredValue"}}])


DIAS_TOLERANCIA = 5   # competência anterior ainda aceita lançamentos atrasados até o dia 25


def competencias_abertas(base, hoje):
    """
    Regra definida pelo usuário em 28/10/2026 — correções só em competência ABERTA:
      - a competência de hoje (21 do mês anterior a 20 do mês) está sempre aberta;
      - a anterior fica aberta só até o dia 25 (boletins do dia 20 lançados com atraso) e só para os
        CRs cujo FAT. TOTAL em FATURAMENTO_COMPILADO ainda é fórmula (valor congelado = fechada);
      - qualquer outra está fechada.
    Retorna (inicio_da_janela, função aberta(cr, competencia)).
    """
    atual_ini = inicio_competencia(hoje)
    atual = competencia_label(hoje)
    anterior_ini = inicio_competencia(atual_ini - timedelta(days=1))
    anterior = competencia_label(anterior_ini)
    usa_anterior = (hoje - atual_ini).days < DIAS_TOLERANCIA
    congeladas = set()
    if usa_anterior:
        v = base.valores(["FATURAMENTO_COMPILADO!A8:P200"], render="FORMULA")[0]
        for r in v:
            r = list(r) + [""] * 16
            if re.match(r"^GN\d{4}$", str(r[0]).strip()) and not str(r[3]).startswith("="):
                congeladas.add((str(r[0]).strip(), str(r[15]).strip()))

    def aberta(cr, comp):
        if comp == atual:
            return True
        return usa_anterior and comp == anterior and (cr, comp) not in congeladas
    return (anterior_ini if usa_anterior else atual_ini), aberta


def atualizar(api, base, contratos, dias=30, gravar=False, log=print, hoje=None):
    """
    Busca no ProdControl os boletins das competências ABERTAS (no máximo `dias` dias para trás)
    e sincroniza CDO_MAQUINAS e CDO_PRODUCAO.
    gravar=False: só compara e devolve o relatório (nada é escrito na planilha).
    """
    hoje = hoje or agora_ms().date()
    ini_aberta, aberta = competencias_abertas(base, hoje)
    ini = max(hoje - timedelta(days=dias - 1), ini_aberta)
    log(f"Janela: {ini:%d/%m/%Y} a {hoje:%d/%m/%Y} (competências abertas)")
    dados = coletar(api, contratos, ini.isoformat(), hoje.isoformat(), log=log)

    avisos = set()
    turmas, pessoas = Cadastro(api, "/classes"), Cadastro(api, "/employees")
    turmas.carregar([(d.get("class") or {}).get("id") for d in dados["odc"]])
    pessoas.carregar([(d.get(k) or {}).get("id") for d in dados["odc"] for k in ("supervisor", "leader")])
    cab = cabecalhos(dados["odc"], turmas, pessoas)
    ativos = Ativos(api)
    ativos.carregar([(m.get("asset") or {}).get("id") for m in dados["maq"]])
    ids_pf = {(x.get("priceFormation") or {}).get("id") for x in dados["maq"] + dados["prod"]} - {None}
    pfs = buscar_formacoes(api, ids_pf)
    log(f"  {len(pfs)} formações de preço carregadas")
    maq = linhas_maquinas(dados, cab, ativos, pfs, avisos)
    prod = linhas_producao(dados, cab, pfs, avisos)
    ignorados = {}
    def filtra(linhas):
        ok = []
        for r in linhas:
            comp = competencia_label(EPOCA + timedelta(days=r["Data"]))
            if aberta(r["CR"], comp):
                ok.append(r)
            else:
                ignorados.setdefault(f"{r['CR']} {comp}", set()).add(r["CDO"])
        return ok
    maq, prod = filtra(maq), filtra(prod)
    for k, v in sorted(ignorados.items()):
        log(f"  {k}: competência fechada — {len(v)} boletins ignorados")
    log(f"Linhas geradas: {len(maq)} máquinas | {len(prod)} produção")

    meta = base.meta()
    folhas = {s["properties"]["title"]: s for s in meta["sheets"]}
    relatorio, reqs = {"janela": [ini.isoformat(), hoje.isoformat()], "avisos": sorted(avisos),
                       "fechadas_ignoradas": {k: len(v) for k, v in ignorados.items()}}, []
    agora = agora_ms()
    serial_agora = (agora - datetime(1899, 12, 30)).total_seconds() / 86400.0
    fonte = f"API PRODCONTROL {agora:%d/%m/%Y %H:%M}"
    for tag, linhas in (("MAQ", maq), ("PROD", prod)):
        cfg = ABAS[tag]
        info = ler_aba(base, cfg)
        plano = comparar(base, cfg, info, linhas)
        relatorio[cfg["nome"]] = {k: plano[k] for k in ("novos", "alterados", "iguais")}
        relatorio[cfg["nome"]]["linhas_gravadas"] = len(plano["gravar"])
        relatorio[cfg["nome"]]["linhas_apagadas"] = len(set(plano["apagar"]))
        relatorio[cfg["nome"]]["detalhe_alterados"] = plano["detalhe"][:20]
        log(f"{cfg['nome']}: {plano['novos']} boletins novos | {plano['alterados']} alterados | "
            f"{plano['iguais']} iguais")
        folha = folhas[cfg["nome"]]
        r, _ = montar_requests(base, cfg, info, plano, folha["properties"]["sheetId"],
                               folha.get("basicFilter"), serial_agora, fonte)
        reqs += r
    relatorio["gravado"] = False
    if gravar and reqs:
        base.batch(reqs)                       # atômico: tudo ou nada
        relatorio["gravado"] = True
        m, p = relatorio["CDO_MAQUINAS"], relatorio["CDO_PRODUCAO"]
        registrar_log(base, "ATUALIZAR API", "AVISO" if avisos else "OK",
                      f"Janela {ini:%d/%m/%Y} a {hoje:%d/%m/%Y} | Máquinas: {m['novos']} novos, "
                      f"{m['alterados']} alterados, {m['linhas_gravadas']} linhas gravadas, "
                      f"{m['linhas_apagadas']} substituídas | Produção: {p['novos']} novos, "
                      f"{p['alterados']} alterados, {p['linhas_gravadas']} linhas gravadas, "
                      f"{p['linhas_apagadas']} substituídas" +
                      (" | ⚠ " + "; ".join(sorted(avisos)[:10]) if avisos else ""))
        log("Base atualizada (gravação atômica concluída).")
    elif gravar:
        log("Nada mudou na base — nenhuma gravação necessária.")
    return relatorio


def buscar_formacoes(api, ids, workers=4):
    """Composição completa (máquinas, implementos, veículos e mão de obra) de cada formação de preço.
    /odc/production só traz a mão de obra; a máquina precisa desta rota."""
    def um(i):
        try:
            return i, api.get(f"/prices-formation/{i}")
        except Exception:
            return i, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return {i: pf for i, pf in ex.map(um, ids) if pf}


def acompanhar_publicacao(token_github, inicio_utc, repo="cilascontroleoperacional-cloud/gnpcp-sistema",
                          workflow="atualizar-dashboards.yml", limite_s=480, intervalo_s=10):
    """Espera a execução disparada (criada após inicio_utc) terminar. Devolve situação + link."""
    h = {"Authorization": f"Bearer {token_github}", "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=5"
    fim = time.time() + limite_s
    link = f"https://github.com/{repo}/actions"
    while time.time() < fim:
        time.sleep(intervalo_s)
        try:
            runs = requests.get(url, headers=h, timeout=30).json().get("workflow_runs", [])
        except Exception:
            continue
        for r in runs:
            criado = datetime.strptime(r["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            if criado >= inicio_utc - timedelta(seconds=10):
                link = r.get("html_url", link)
                if r.get("status") == "completed":
                    return {"situacao": "sucesso" if r.get("conclusion") == "success" else "falha", "link": link}
                break
    return {"situacao": "tempo esgotado", "link": link}


def disparar_dashboards(token_github, repo="cilascontroleoperacional-cloud/gnpcp-sistema",
                        workflow="atualizar-dashboards.yml", publicar=True):
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
                      headers={"Authorization": f"Bearer {token_github}",
                               "Accept": "application/vnd.github+json"},
                      json={"ref": "main", "inputs": {"publicar": "true" if publicar else "false"}},
                      timeout=30)
    if r.status_code != 204:
        raise RuntimeError(f"GitHub recusou o disparo ({r.status_code}): {r.text[:200]}")
