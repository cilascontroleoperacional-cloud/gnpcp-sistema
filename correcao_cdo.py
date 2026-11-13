"""
Correção diária de CDOs (ProdControl) — detectar divergências e aplicar correções aprovadas.

Regras (definidas pelo analista de PCP em 13/11/2026 — ver claude/CORRECAO_CDO_2026-11-13.md):
  R1  Horas por grupo de função têm de fechar em 100% exato:
        horas apontadas na PRODUÇÃO (trabalhadas + improdutivas)
        = jornada dos PRESENTES na MÃO DE OBRA que são do cadastro da turma
      (igual ao painel APONTAMENTOS_GERAL: colaborador emprestado de outra turma não conta).
      Grupos: Trabalhadores Florestais, Operadores, Motoristas (encarregado e demais ficam fora).
  R2  Motorista em turma SEM veículo no cadastro (e sem veículo apontado no CDO): as horas
      trabalhadas viram horas improdutivas, mantendo a operação. Correção automática (com
      aprovação) via PUT /odc/production/{id}.
  R3  Todo colaborador cadastrado na turma na data tem de estar na MÃO DE OBRA do CDO.
  R4  Toda máquina, veículo (exceto veículo leve) e implemento cadastrado na turma na data tem
      de estar apontado na aba MÁQUINAS.
  R5  A PRODUÇÃO é a referência. Por operação + talhão, as horas trabalhadas e as paralisações
      das MÁQUINAS (e dos IMPLEMENTOS) têm de ser iguais às horas trabalhadas e improdutivas dos
      OPERADORES. Veículos x motoristas: comparação pelo total do CDO. Máquina parada o dia todo
      (0 h trabalhada) em operação sem operador na PRODUÇÃO não é erro.
  R6  Horímetro: final - inicial = horas trabalhadas da linha; as linhas do dia formam sequência;
      o primeiro inicial do dia = último final apontado antes (até 10 dias para trás).
  R7  Linha de PRODUÇÃO com hora trabalhada e produção zerada (fora de apoio/manutenção).
  Só a R2 grava; as demais apontam a linha e a correção sugerida.

Fontes na API:
  /odc, /odc/machine, /odc/production   filtram por contractId + startDate/endDate
  /odc/worker                           por CDO (operationDailyControlId)
  /employees?classId&contractId&date    cadastro de colaboradores da turma na data (DD/MM/YYYY)
  /assets?class&contractId&date&resources=true   cadastro de equipamentos da turma na data

Nada aqui grava sem passar por aplicar(): cada correção é conferida de novo contra o
ProdControl imediatamente antes do PUT e só segue se a linha continuar igual à detectada.
"""
import hashlib
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urlencode

TOL = 0.005            # horas — só 100% exato é aceito (tolerância apenas de arredondamento)
DIAS_HORIMETRO = 10    # quantos dias para trás procurar o último horímetro de cada máquina

# Palavras (sem acento, minúsculas) que identificam VEÍCULO quando o cadastro não traz a categoria.
VEICULO_PALAVRAS = ("caminh", "onibus", "microonibus", "micro-onibus", "van ", "comboio",
                    "pipa", "munck", "prancha", "carreta", "cavalo mec", "basculante")
VEICULO_EXCLUIR = ("leve",)

GRUPOS = (("OPERADORES", ("operador",)),
          ("MOTORISTAS", ("motorista",)),
          ("TRABALHADORES FLORESTAIS", ("trabalhador",)))

# operações que por natureza não têm produção (R7 não se aplica)
OPERACAO_SEM_PRODUCAO = ("apoio", "manut", "administr")

ROTULO = {"MAQUINAS": "MÁQUINAS", "VEICULOS": "VEÍCULOS", "IMPLEMENTOS": "IMPLEMENTOS"}


# ------------------------------------------------------------------ utilitários
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def num(v):
    """Aceita 8, 8.0, '8', '8,00', '1.234,50', None."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def r2(x):
    return round(float(x) + 1e-9, 2)


def fmt(x):
    """Número no padrão brasileiro, sem zeros à direita: 3065 -> '3.065', 6.58 -> '6,58'."""
    s = f"{r2(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.rstrip("0").rstrip(",") if "," in s else s


def grupo_funcao(nome):
    n = norm(nome)
    for grupo, prefixos in GRUPOS:
        if any(n.startswith(p) for p in prefixos):
            return grupo
    return None


def eh_veiculo(tipo_nome):
    n = norm(tipo_nome) + " "
    if any(x in n for x in VEICULO_EXCLUIR):
        return False
    return any(p in n for p in VEICULO_PALAVRAS)


def categoria_equip(resource_type):
    """MAQUINAS | VEICULOS | IMPLEMENTOS | VL (veículo leve, ignorado) a partir de
    asset.resourceType {name, type{name}} — type.name vem do cadastro ("Máquinas", "Implementos"...)."""
    rt = resource_type or {}
    tipo, nome = norm(_sub(rt, "type", "name")), norm(rt.get("name"))
    if tipo.startswith("implement"):
        return "IMPLEMENTOS"
    if tipo.startswith("veicul"):
        return "VL" if ("leve" in nome or nome in ("vl", "veiculo")) else "VEICULOS"
    if tipo.startswith("maquin"):
        return "MAQUINAS"
    if "veiculo leve" in nome:
        return "VL"
    return "VEICULOS" if eh_veiculo(nome) else "MAQUINAS"


def presente(tipo_nome):
    return norm(tipo_nome).startswith("presen")


def _id(*partes):
    return hashlib.sha1("|".join(str(p) for p in partes).encode()).hexdigest()[:12]


def _sub(d, *caminho):
    for k in caminho:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def odc_id_de(item):
    return item.get("operationDailyControlId") or _sub(item, "operationDailyControl", "id")


def operacao_de(item):
    """(código, nome) da operação de uma linha de produção ou de máquina."""
    op = _sub(item, "priceFormation", "operation") or item.get("operation") or {}
    return str(op.get("code") or "").strip(), op.get("name") or ""


def chave_op_talhao(item):
    cod, nome = operacao_de(item)
    return norm(cod or nome), norm(_sub(item, "plot", "name"))


def paginar(api, path, params, limite=255):
    out, page = [], 1
    while True:
        q = dict(params, limit=limite, page=page)
        d = api.get(f"{path}?{urlencode(q)}")
        out += d.get("items", [])
        if page >= (d.get("meta") or {}).get("totalPages", 1):
            return out
        page += 1


# ------------------------------------------------------------------ coleta
def coletar(api, contratos, ini_iso, fim_iso, log=print):
    """Cabeçalhos, máquinas e produção por contrato/período; mão de obra e cadastro por CDO.
    Cabeçalhos e máquinas vêm também dos DIAS_HORIMETRO dias anteriores (sequência do horímetro).
    Qualquer falha de leitura dos CDOs interrompe tudo (nunca analisar com dado incompleto)."""
    antes_iso = (datetime.strptime(ini_iso, "%Y-%m-%d") - timedelta(days=DIAS_HORIMETRO)).strftime("%Y-%m-%d")
    rotas = (("/odc", antes_iso), ("/odc/machine", antes_iso), ("/odc/production", ini_iso))
    tarefas = [(c["contractId"], r, d) for c in contratos for r, d in rotas]

    def um(t):
        cid, rota, desde = t
        return paginar(api, rota, {"contractId": cid, "startDate": desde, "endDate": fim_iso})
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = {(t[0], t[1]): v for t, v in zip(tarefas, ex.map(um, tarefas))}

    cdos, historico = [], {}      # historico: asset_id -> [(data, horímetro final, código do CDO)]
    for c in contratos:
        cab, maq, prod = (res[(c["contractId"], r)] for r, _ in rotas)
        data_de = {h["id"]: (h.get("bulletinDate") or "")[:10] for h in cab}
        cod_de = {h["id"]: h.get("code") for h in cab}
        por_maq, por_prod = {}, {}
        for m in maq:
            oid = odc_id_de(m)
            d = data_de.get(oid, "")
            if d and d < ini_iso:
                aid, fim = _sub(m, "asset", "id"), num(m.get("hourMeterEnd"))
                if aid and fim > 0:
                    historico.setdefault(aid, []).append((d, fim, cod_de.get(oid)))
            else:
                por_maq.setdefault(oid, []).append(m)
        for p in prod:
            por_prod.setdefault(odc_id_de(p), []).append(p)
        do_periodo = [h for h in cab if ini_iso <= (h.get("bulletinDate") or "")[:10] <= fim_iso]
        for h in do_periodo:
            cdos.append({"cab": h, "contrato": c["nome"], "contractId": c["contractId"],
                         "maq": por_maq.get(h["id"], []), "prod": por_prod.get(h["id"], [])})
        log(f"  {c['nome']}: {len(do_periodo)} CDOs | "
            f"{sum(len(por_maq.get(h['id'], [])) for h in do_periodo)} máquinas | {len(prod)} produções")

    # horímetro "anterior" de cada máquina em cada CDO: último final apontado antes da data do CDO
    # (inclui CDOs do próprio período em datas anteriores, quando a conferência cobre vários dias)
    for cdo in cdos:
        d = (cdo["cab"].get("bulletinDate") or "")[:10]
        for m in cdo["maq"]:
            aid, fim = _sub(m, "asset", "id"), num(m.get("hourMeterEnd"))
            if aid and fim > 0:
                historico.setdefault(aid, []).append((d, fim, cdo["cab"].get("code")))
    for cdo in cdos:
        d = (cdo["cab"].get("bulletinDate") or "")[:10]
        ant = {}
        for m in cdo["maq"]:
            aid = _sub(m, "asset", "id")
            antes = [x for x in historico.get(aid, []) if x[0] < d]
            if antes:
                ultimo_dia = max(x[0] for x in antes)
                ant[aid] = max((x for x in antes if x[0] == ultimo_dia), key=lambda x: x[1])
        cdo["horimetro_anterior"] = ant

    def mao_de_obra(cdo):
        return paginar(api, "/odc/worker",
                       {"operationDailyControlId": cdo["cab"]["id"], "deletedAt": "true"}, limite=4999)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for cdo, w in zip(cdos, ex.map(mao_de_obra, cdos)):
            cdo["mdo"] = w
    log(f"  Mão de obra lida de {len(cdos)} CDOs.")

    # cadastro da turma na data (1 consulta por turma+data) — se falhar, o CDO segue sem R3/R4
    chaves = {}
    for cdo in cdos:
        cab = cdo["cab"]
        cls, d = _sub(cab, "class", "id") or cab.get("classId"), (cab.get("bulletinDate") or "")[:10]
        cdo["_chave"] = (cdo["contractId"], cls, d) if cls and len(d) == 10 else None
        if cdo["_chave"]:
            chaves[cdo["_chave"]] = None

    def cadastro(ch):
        cid, cls, d = ch
        data_br = f"{d[8:10]}/{d[5:7]}/{d[0:4]}"
        try:
            emps = paginar(api, "/employees", {"classId": cls, "contractId": cid, "date": data_br,
                                               "deletedAt": "false"})
            ativos = paginar(api, "/assets", {"class": cls, "contractId": cid, "date": data_br,
                                              "resources": "true", "deletedAt": "false"})
            return {"colaboradores": emps, "equipamentos": ativos}
        except Exception as e:
            return {"erro": str(e)[:150]}
    lista = list(chaves)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for ch, cad in zip(lista, ex.map(cadastro, lista)):
            chaves[ch] = cad
    falhas = 0
    for cdo in cdos:
        cad = chaves.get(cdo.pop("_chave")) if cdo.get("_chave") else {"erro": "CDO sem turma/data"}
        cdo["cadastro"] = cad
        falhas += 1 if cad.get("erro") else 0
    log(f"  Cadastro de {len(lista)} turmas lido" + (f" ({falhas} CDOs sem cadastro)." if falhas else "."))
    return cdos


# ------------------------------------------------------------------ leitura dos itens
def linha_producao(p):
    rt = p.get("resourceType") or {}
    cod, nome = operacao_de(p)
    return {
        "id": p.get("id"),
        "funcao": rt.get("name") or rt.get("description") or "",
        "funcao_cod": rt.get("code"),
        "resourceTypeId": p.get("resourceTypeId") or rt.get("id"),
        "operacao": nome, "operacao_cod": cod,
        "projeto": _sub(p, "project", "name") or "",
        "talhao": _sub(p, "plot", "name") or "",
        "chave": chave_op_talhao(p),
        "ht": num(p.get("workedHours")),
        "hi": num(p.get("unproductiveHours")),
        "producao": num(p.get("productiveAmount")),
        "qtd": p.get("totalEmployees"),
    }


def corpo_put_producao(p, ht, hi, resolver_operacao=None):
    """Objeto COMPLETO exigido pelo PUT /odc/production/{id} (12 campos, igual ao que o site envia).
    Devolve (corpo, faltando) — se faltar algum id, a correção não é oferecida.
    resolver_operacao(priceFormationId) -> operationId, usado só se a lista não trouxer a operação."""
    pf = p.get("priceFormation") or {}
    corpo = {
        "id": p.get("id"),
        "operationDailyControlId": odc_id_de(p),
        "operationId": p.get("operationId") or _sub(p, "operation", "id") or _sub(pf, "operation", "id"),
        "plotId": p.get("plotId") or _sub(p, "plot", "id"),
        "priceFormationId": p.get("priceFormationId") or pf.get("id"),
        "productiveAmount": num(p.get("productiveAmount")),
        "projectId": p.get("projectId") or _sub(p, "project", "id"),
        "resourceTypeId": p.get("resourceTypeId") or _sub(p, "resourceType", "id"),
        "statusId": p.get("statusId") or _sub(p, "status", "id"),
        "totalEmployees": p.get("totalEmployees"),
        "unproductiveHours": r2(hi),
        "workedHours": r2(ht),
    }
    if not corpo["operationId"] and resolver_operacao and corpo["priceFormationId"]:
        corpo["operationId"] = resolver_operacao(corpo["priceFormationId"])
    faltando = [k for k, v in corpo.items() if v is None or v == ""]
    return corpo, faltando


# ------------------------------------------------------------------ regras
def analisar_cdo(cdo, resolver_operacao=None, resolver_tipo_ativo=None):
    cab = cdo["cab"]
    info = {
        "cdo_id": cab["id"], "cdo": cab.get("code"), "data": (cab.get("bulletinDate") or "")[:10],
        "contrato": cdo["contrato"],
        "encarregado": _sub(cab, "leader", "name") or "",
        "supervisor": _sub(cab, "supervisor", "name") or "",
        "turma": _sub(cab, "class", "name") or _sub(cab, "class", "description") or "",
        "criado_por": _sub(cab, "createdBy", "name") or "",
        "cr": _sub(cab, "class", "costCenter", "name") or "",
        "criado_em": cab.get("createdAt") or "",
    }
    achados = []

    cad = cdo.get("cadastro") or {"erro": "cadastro não consultado"}
    cad_ok = not cad.get("erro")
    avisos = [] if cad_ok else [f"Cadastro da turma indisponível ({cad['erro']}): sem conferência de "
                                "colaboradores/equipamentos cadastrados."]
    da_turma = {e.get("id") for e in (cad.get("colaboradores") or [])}

    # --- mão de obra
    mdo = []
    for w in cdo.get("mdo", []):
        emp = w.get("employee") or {}
        func = _sub(emp, "resourceType", "name") or ""
        mdo.append({"id": w.get("id"), "emp_id": emp.get("id"), "nome": emp.get("name") or "",
                    "matricula": emp.get("employeeNumber"), "funcao": func, "grupo": grupo_funcao(func),
                    "tipo": _sub(w, "type", "name") or "", "jornada": num(w.get("dailyJourney")),
                    "da_turma": (emp.get("id") in da_turma) if cad_ok else True})
    prods = [dict(linha_producao(p), bruto=p) for p in cdo.get("prod", [])]
    for p in prods:
        p["grupo"] = grupo_funcao(p["funcao"])

    # --- equipamentos
    cad_equip = []
    for a in (cad.get("equipamentos") or []):
        cad_equip.append({"id": a.get("id"), "codigo": a.get("code") or "",
                          "tipo": _sub(a, "resourceType", "name") or "",
                          "categoria": categoria_equip(a.get("resourceType"))})
    cat_por_ativo = {e["id"]: e["categoria"] for e in cad_equip}

    equip = []
    for m in cdo.get("maq", []):
        asset = m.get("asset") or {}
        paradas = m.get("odcMachineStoppages") or []
        # categoria: cadastro da turma > tipo que veio na linha > consulta ao patrimônio (/assets/{id})
        rtipo = asset.get("resourceType") or {}
        cat = cat_por_ativo.get(asset.get("id"))
        if not cat and not _sub(rtipo, "type", "name") and resolver_tipo_ativo and asset.get("id"):
            rtipo = resolver_tipo_ativo(asset["id"]) or rtipo
        confiavel = bool(cat or _sub(rtipo, "type", "name"))
        cod_op, nome_op = operacao_de(m)
        equip.append({
            "asset_id": asset.get("id"), "codigo": asset.get("code") or "",
            "categoria": cat or categoria_equip(rtipo), "confiavel": confiavel,
            "operacao": nome_op, "operacao_cod": cod_op, "talhao": _sub(m, "plot", "name") or "",
            "chave": chave_op_talhao(m),
            "ht": num(m.get("workedHours")),
            "paradas": sum(num(s.get("time")) for s in paradas),
            "ini": num(m.get("hourMeterStart")), "fim": num(m.get("hourMeterEnd")),
        })
    tem_veiculo = (any(e["categoria"] == "VEICULOS" for e in equip)
                   or any(e["categoria"] == "VEICULOS" for e in cad_equip))

    # --- R1: 100% por grupo (presentes = só quem é do cadastro da turma, como no painel)
    for grupo, _ in GRUPOS:
        do_grupo = [w for w in mdo if w["grupo"] == grupo]
        pres = [w for w in do_grupo if w["da_turma"] and presente(w["tipo"])]
        aus = [w for w in do_grupo if w["da_turma"] and not presente(w["tipo"])]
        fora = [w for w in do_grupo if not w["da_turma"]]
        h_pres = r2(sum(w["jornada"] for w in pres))
        h_apont = r2(sum(p["ht"] + p["hi"] for p in prods if p["grupo"] == grupo))
        if abs(h_pres - h_apont) <= TOL:
            continue
        dif = r2(h_apont - h_pres)
        pct = None if h_pres == 0 else round(h_apont / h_pres * 100)
        dicas = []
        if dif > 0:
            exatos = [w for w in aus if abs(w["jornada"] - dif) <= TOL]
            if exatos:
                dicas.append("Excesso igual à jornada de quem está ausente: " +
                             "; ".join(f"{w['nome']} ({w['tipo']}, {fmt(w['jornada'])} h)" for w in exatos) +
                             f" — se trabalhou, marcar Presente; senão, reduzir {fmt(dif)} h na PRODUÇÃO.")
            elif aus:
                dicas.append("Ausentes no grupo: " +
                             "; ".join(f"{w['nome']} ({w['tipo']}, {fmt(w['jornada'])} h)" for w in aus) + ".")
            if not pres and not aus:
                dicas.append("Nenhum colaborador da turma neste grupo na MÃO DE OBRA — falta lançar quem trabalhou.")
            elif not exatos:
                dicas.append(f"Reduzir {fmt(dif)} h na PRODUÇÃO ou marcar Presente quem da turma trabalhou.")
        else:
            dicas.append(f"Faltam {fmt(-dif)} h a apontar na PRODUÇÃO (trabalhadas ou improdutivas) "
                         f"para: " + "; ".join(f"{w['nome']} ({fmt(w['jornada'])} h)" for w in pres) + ".")
        if fora:
            dicas.append("De outra turma (não entram na conta, como no painel): " +
                         "; ".join(f"{w['nome']} ({w['tipo']}, {fmt(w['jornada'])} h)" for w in fora) + ".")
        achados.append({
            "id": _id("R1", cab["id"], grupo), "regra": "R1", "tipo": "revisar", "grupo": grupo,
            "titulo": f"{grupo}: {fmt(h_apont)} h apontadas x {fmt(h_pres)} h presentes"
                      + (f" ({pct}%)" if pct is not None else ""),
            "horas_presentes": h_pres, "horas_apontadas": h_apont, "diferenca": dif,
            "deducao": dicas,
            "presentes": [{"nome": w["nome"], "funcao": w["funcao"], "jornada": w["jornada"]} for w in pres],
            "ausentes": [{"nome": w["nome"], "funcao": w["funcao"], "tipo": w["tipo"],
                          "jornada": w["jornada"]} for w in aus],
            "linhas": [{"funcao": p["funcao"], "operacao": p["operacao"], "talhao": p["talhao"],
                        "ht": p["ht"], "hi": p["hi"]} for p in prods if p["grupo"] == grupo],
        })

    # --- R2: motorista sem veículo -> horas improdutivas
    if not tem_veiculo:
        for p in prods:
            if p["grupo"] != "MOTORISTAS" or p["ht"] <= TOL:
                continue
            novo_ht, novo_hi = 0.0, r2(p["hi"] + p["ht"])
            corpo, faltando = corpo_put_producao(p["bruto"], novo_ht, novo_hi, resolver_operacao)
            achado = {
                "id": _id("R2", p["id"], p["ht"], p["hi"]), "regra": "R2", "grupo": "MOTORISTAS",
                "titulo": f"Motorista sem veículo no CDO: {fmt(p['ht'])} h trabalhadas → improdutivas "
                          f"({p['operacao']}, talhão {p['talhao']})",
                "linha_id": p["id"],
                "antes": {"workedHours": r2(p["ht"]), "unproductiveHours": r2(p["hi"])},
                "depois": {"workedHours": novo_ht, "unproductiveHours": novo_hi},
            }
            if faltando:
                achado.update(tipo="revisar",
                              deducao=["Correção manual: a API não devolveu " + ", ".join(faltando) + "."])
            elif not cad_ok:
                achado.update(tipo="revisar",
                              deducao=["Não consegui confirmar no cadastro que a turma não tem veículo; "
                                       "conferir antes de passar as horas para improdutivas."])
            else:
                achado.update(tipo="corrigir", metodo="PUT", rota=f"/odc/production/{p['id']}", corpo=corpo)
            achados.append(achado)

    # --- R3: colaborador cadastrado na turma e fora da MÃO DE OBRA
    if cad_ok:
        lancados = {w["emp_id"] for w in mdo}
        fora = [e for e in cad["colaboradores"] if e.get("id") not in lancados]
        if fora:
            nomes = [{"nome": e.get("name") or "", "matricula": e.get("employeeNumber"),
                      "funcao": _sub(e, "resourceType", "name") or ""} for e in fora]
            achados.append({
                "id": _id("R3", cab["id"], *sorted(str(e.get("id")) for e in fora)), "regra": "R3",
                "tipo": "revisar", "grupo": "MÃO DE OBRA",
                "titulo": f"{len(fora)} colaborador(es) da turma fora da MÃO DE OBRA",
                "deducao": ["Lançar com a presença/ausência correta: " +
                            "; ".join(f"{n['nome']} ({n['funcao']})" for n in nomes) + "."],
                "colaboradores": nomes})

    # --- R4: equipamento cadastrado na turma e não apontado
    if cad_ok:
        apontados = {e["asset_id"] for e in equip}
        fora = [e for e in cad_equip if e["categoria"] != "VL" and e["id"] not in apontados]
        if fora:
            achados.append({
                "id": _id("R4", cab["id"], *sorted(str(e["id"]) for e in fora)), "regra": "R4",
                "tipo": "revisar", "grupo": "EQUIPAMENTOS",
                "titulo": f"{len(fora)} equipamento(s) da turma sem apontamento na aba MÁQUINAS",
                "deducao": ["Apontar (horas trabalhadas ou parada): " +
                            "; ".join(f"{e['codigo']} ({e['tipo']})" for e in fora) + "."],
                "equipamentos": [{k: e[k] for k in ("codigo", "tipo", "categoria")} for e in fora]})

    # --- R5: MÁQUINAS (e implementos) x PRODUÇÃO dos operadores, por operação + talhão
    duvidosos = [e["codigo"] for e in equip if not e["confiavel"]]
    if duvidosos:        # sem saber se é máquina, veículo ou implemento a conta sairia errada
        avisos.append("Horas de equipamento x função não conferidas: categoria desconhecida de "
                      + ", ".join(sorted(set(duvidosos))) + ".")
    else:
        prod_op = {}
        for p in prods:
            if p["grupo"] == "OPERADORES":
                x = prod_op.setdefault(p["chave"], {"ht": 0.0, "hi": 0.0, "operacao": p["operacao"],
                                                    "operacao_cod": p["operacao_cod"], "talhao": p["talhao"]})
                x["ht"] += p["ht"]
                x["hi"] += p["hi"]
        for cat in ("MAQUINAS", "IMPLEMENTOS"):
            linhas_eq = [e for e in equip if e["categoria"] == cat]
            if not linhas_eq:
                continue                  # falta de apontamento do equipamento é a R4
            eq = {}
            for e in linhas_eq:
                x = eq.setdefault(e["chave"], {"ht": 0.0, "par": 0.0, "cods": [], "operacao": e["operacao"],
                                               "operacao_cod": e["operacao_cod"], "talhao": e["talhao"]})
                x["ht"] += e["ht"]
                x["par"] += e["paradas"]
                if e["codigo"] not in x["cods"]:
                    x["cods"].append(e["codigo"])
            problemas, itens = [], []
            for ch in sorted(set(eq) | set(prod_op)):
                m, p = eq.get(ch), prod_op.get(ch)
                ref = m or p
                onde = f"{ref['operacao_cod'] or ref['operacao']} talhão {ref['talhao']}"
                if m and not p:
                    if m["ht"] > TOL:
                        problemas.append(f"{'/'.join(m['cods'])} ({onde}): {fmt(m['ht'])} h trabalhadas sem "
                                         "produção de operador nessa operação e talhão.")
                        itens.append({"onde": onde, "equipamentos": m["cods"], "maquina": [r2(m["ht"]), r2(m["par"])],
                                      "producao": [0.0, 0.0]})
                    continue              # parada o dia todo sem operador: não é erro
                if p and not m:
                    if cat == "MAQUINAS" and p["ht"] > TOL:
                        problemas.append(f"{onde}: operadores com {fmt(p['ht'])} h trabalhadas na PRODUÇÃO e "
                                         "nenhuma máquina apontada nessa operação e talhão.")
                        itens.append({"onde": onde, "equipamentos": [], "maquina": [0.0, 0.0],
                                      "producao": [r2(p["ht"]), r2(p["hi"])]})
                    continue
                if abs(m["ht"] - p["ht"]) > TOL or abs(m["par"] - p["hi"]) > TOL:
                    problemas.append(
                        f"{'/'.join(m['cods'])} ({onde}): {fmt(m['ht'])} h trabalhadas e {fmt(m['par'])} h paradas; "
                        f"na PRODUÇÃO são {fmt(p['ht'])} h trabalhadas e {fmt(p['hi'])} h improdutivas. "
                        f"Ajustar a aba MÁQUINAS para {fmt(p['ht'])} h trabalhadas e {fmt(p['hi'])} h de paralisação.")
                    itens.append({"onde": onde, "equipamentos": m["cods"], "maquina": [r2(m["ht"]), r2(m["par"])],
                                  "producao": [r2(p["ht"]), r2(p["hi"])]})
            if problemas:
                achados.append({
                    "id": _id("R5", cab["id"], cat), "regra": "R5", "tipo": "revisar", "grupo": ROTULO[cat],
                    "titulo": f"{ROTULO[cat]} x PRODUÇÃO: {len(problemas)} linha(s) com horas diferentes",
                    "deducao": problemas, "itens": itens})

        # veículos x motoristas: pelo total do CDO
        veic = [e for e in equip if e["categoria"] == "VEICULOS"]
        if veic or any(e["categoria"] == "VEICULOS" for e in cad_equip):
            ht_f = r2(sum(p["ht"] for p in prods if p["grupo"] == "MOTORISTAS"))
            hi_f = r2(sum(p["hi"] for p in prods if p["grupo"] == "MOTORISTAS"))
            ht_e, par = r2(sum(e["ht"] for e in veic)), r2(sum(e["paradas"] for e in veic))
            problemas = []
            if abs(ht_e - ht_f) > TOL:
                problemas.append(f"Horas trabalhadas: VEÍCULOS {fmt(ht_e)} h x MOTORISTAS {fmt(ht_f)} h.")
            if abs(par - hi_f) > TOL:
                problemas.append(f"Paralisações de VEÍCULOS {fmt(par)} h x improdutivas de MOTORISTAS {fmt(hi_f)} h.")
            if problemas:
                achados.append({
                    "id": _id("R5", cab["id"], "VEICULOS"), "regra": "R5", "tipo": "revisar", "grupo": "VEÍCULOS",
                    "titulo": "VEÍCULOS x MOTORISTAS: horas não batem", "deducao": problemas})

    # --- R6: horímetro (linha, sequência do dia e continuidade com o último apontamento)
    anterior = cdo.get("horimetro_anterior") or {}
    por_ativo = {}
    for e in equip:
        if e["categoria"] in ("MAQUINAS", "VEICULOS") and (e["ini"] > 0 or e["fim"] > 0):
            por_ativo.setdefault(e["asset_id"], []).append(e)
    problemas = []
    for aid, linhas in por_ativo.items():
        cod = linhas[0]["codigo"]
        linhas = sorted(linhas, key=lambda e: (e["ini"], e["fim"]))
        for e in linhas:
            if abs((e["fim"] - e["ini"]) - e["ht"]) > TOL:
                problemas.append(f"{cod} (talhão {e['talhao']}): horímetro {fmt(e['ini'])} → {fmt(e['fim'])} "
                                 f"= {fmt(e['fim'] - e['ini'])} h, mas a linha tem {fmt(e['ht'])} h trabalhadas.")
        for a, b in zip(linhas, linhas[1:]):
            if abs(b["ini"] - a["fim"]) > TOL:
                problemas.append(f"{cod}: linha do talhão {b['talhao']} começa em {fmt(b['ini'])}, mas a anterior "
                                 f"(talhão {a['talhao']}) terminou em {fmt(a['fim'])}.")
        ant = anterior.get(aid)
        if ant and abs(linhas[0]["ini"] - ant[1]) > TOL:
            d = ant[0]
            problemas.append(f"{cod}: o dia começa em {fmt(linhas[0]['ini'])}, mas o último horímetro apontado foi "
                             f"{fmt(ant[1])} (CDO {ant[2]} de {d[8:10]}/{d[5:7]}).")
    if problemas:
        achados.append({
            "id": _id("R6", cab["id"]), "regra": "R6", "tipo": "revisar", "grupo": "HORÍMETRO",
            "titulo": f"Horímetro: {len(problemas)} divergência(s)", "deducao": problemas})

    # --- R7: produção com hora trabalhada e quantidade zerada
    sem_prod = [p for p in prods if p["grupo"] in ("OPERADORES", "TRABALHADORES FLORESTAIS")
                and p["ht"] > TOL and p["producao"] <= TOL
                and not any(x in norm(p["operacao"]) for x in OPERACAO_SEM_PRODUCAO)]
    if sem_prod:
        achados.append({
            "id": _id("R7", cab["id"], *sorted(str(p["id"]) for p in sem_prod)), "regra": "R7",
            "tipo": "revisar", "grupo": "PRODUÇÃO",
            "titulo": f"{len(sem_prod)} linha(s) de PRODUÇÃO com hora trabalhada e produção zerada",
            "deducao": ["; ".join(f"{p['operacao_cod'] or p['operacao']} talhão {p['talhao']} ({p['funcao']}, "
                                  f"{fmt(p['ht'])} h)" for p in sem_prod) + "."]})

    return dict(info, tem_veiculo=tem_veiculo, cadastro_ok=cad_ok, avisos=avisos, achados=achados)


REGRAS = ("R1", "R2", "R3", "R4", "R5", "R6", "R7")


def detectar(api, contratos, ini_iso, fim_iso, log=print):
    log(f"Correção de CDO: lendo {ini_iso} a {fim_iso}...")
    cdos = coletar(api, contratos, ini_iso, fim_iso, log)
    cache = {}

    def resolver(pf_id):
        if pf_id not in cache:
            try:
                pf = api.get(f"/prices-formation/{pf_id}")
                cache[pf_id] = pf.get("operationId") or _sub(pf, "operation", "id")
            except Exception:
                cache[pf_id] = None
        return cache[pf_id]
    cache_ativo = {}

    def resolver_ativo(asset_id):
        if asset_id not in cache_ativo:
            try:
                cache_ativo[asset_id] = api.get(f"/assets/{asset_id}").get("resourceType")
            except Exception:
                cache_ativo[asset_id] = None
        return cache_ativo[asset_id]
    analises = [analisar_cdo(c, resolver, resolver_ativo) for c in cdos]
    com = [a for a in analises if a["achados"] or a["avisos"]]
    com.sort(key=lambda a: (a["contrato"], a["data"], str(a["cdo"])))
    todos = [x for a in com for x in a["achados"]]
    resumo = {
        "periodo": [ini_iso, fim_iso], "cdos_lidos": len(analises),
        "cdos_com_divergencia": sum(1 for a in analises if a["achados"]),
        "corrigir": sum(1 for x in todos if x["tipo"] == "corrigir"),
        "revisar": sum(1 for x in todos if x["tipo"] == "revisar"),
        "por_regra": {r: sum(1 for x in todos if x["regra"] == r) for r in REGRAS},
        "cdos_sem_cadastro": sum(1 for a in analises if a["avisos"] and not a["cadastro_ok"]),
        "por_contrato": {},
    }
    for a in analises:
        pc = resumo["por_contrato"].setdefault(a["contrato"], {"cdos": 0, "com_divergencia": 0})
        pc["cdos"] += 1
        pc["com_divergencia"] += 1 if a["achados"] else 0
    log(f"  {resumo['cdos_lidos']} CDOs lidos; {resumo['cdos_com_divergencia']} com divergência "
        f"({resumo['corrigir']} correções prontas, {resumo['revisar']} para revisar).")
    # "todos" (um resumo por CDO, com ou sem divergência) alimenta o ranking de apontamentos
    return {"resumo": resumo, "cdos": com,
            "todos": [{k: a[k] for k in ("cdo", "data", "contrato", "encarregado", "supervisor", "turma",
                                         "criado_por", "criado_em", "cr", "cadastro_ok")}
                      | {"regras": sorted({x["regra"] for x in a["achados"]})} for a in analises]}


# ------------------------------------------------------------------ aplicar
def _linha_atual(api, achado):
    """Relê a linha no ProdControl agora (lista do CDO — rota já usada pelo site)."""
    odc = achado["corpo"]["operationDailyControlId"]
    itens = paginar(api, "/odc/production", {"operationDailyControlId": odc, "deletedAt": "true"}, limite=4999)
    return next((p for p in itens if p.get("id") == achado["linha_id"]), None)


def aplicar(api, deteccao, ids, log=print):
    """Grava SOMENTE achados 'corrigir' da última detecção cujos ids foram aprovados.
    Antes de cada PUT relê a linha; se alguém já mexeu (horas diferentes das detectadas), pula.
    Nunca repete um PUT: se a resposta falhar, o item fica como 'conferir' para revisão manual."""
    indice = {x["id"]: (a, x) for a in deteccao["cdos"] for x in a["achados"]}
    saida = []
    for i in dict.fromkeys(ids):
        if i not in indice:
            saida.append({"id": i, "situacao": "ignorado", "motivo": "id não está na última detecção"})
            continue
        a, x = indice[i]
        base = {"id": i, "cdo": a["cdo"], "contrato": a["contrato"], "data": a["data"], "titulo": x["titulo"]}
        if x["tipo"] != "corrigir":
            saida.append(dict(base, situacao="ignorado", motivo="item é só para revisão manual"))
            continue
        try:
            atual = _linha_atual(api, x)
        except Exception as e:
            saida.append(dict(base, situacao="erro", motivo=f"não consegui reler a linha: {str(e)[:150]}"))
            continue
        if atual is None:
            saida.append(dict(base, situacao="pulado", motivo="linha não existe mais no CDO"))
            continue
        agora = {"workedHours": r2(num(atual.get("workedHours"))),
                 "unproductiveHours": r2(num(atual.get("unproductiveHours")))}
        if agora != x["antes"]:
            saida.append(dict(base, situacao="pulado",
                              motivo=f"linha mudou desde a detecção (agora {agora}); detectar de novo"))
            continue
        try:
            resp = api.put(x["rota"], x["corpo"])
        except Exception as e:
            saida.append(dict(base, situacao="conferir", antes=x["antes"], depois=x["depois"],
                              motivo=f"PUT sem confirmação ({str(e)[:150]}) — conferir no ProdControl"))
            log(f"  CDO {a['cdo']}: PUT sem confirmação — conferir manualmente.")
            continue
        gravado = {"workedHours": r2(num((resp or {}).get("workedHours"))),
                   "unproductiveHours": r2(num((resp or {}).get("unproductiveHours")))}
        ok = gravado == x["depois"]
        saida.append(dict(base, situacao="aplicado" if ok else "conferir", antes=x["antes"],
                          depois=gravado, **({} if ok else {"motivo": "resposta diferente do esperado"})))
        log(f"  CDO {a['cdo']} ({a['contrato']}): {x['antes']} -> {gravado}")
    return {"aplicados": sum(1 for s in saida if s["situacao"] == "aplicado"),
            "total": len(saida), "itens": saida}
