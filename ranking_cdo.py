"""
Ranking de apontamentos dos encarregados — grava na planilha Google RANKING_APONTAMENTOS_2026
(aba BASE_APONTAMENTOS) uma linha por encarregado por dia, a partir da conferência de CDOs.

A nota é do apontamento ORIGINAL: a linha é gravada na primeira conferência do dia e nunca é
sobrescrita (rodar a conferência ANTES de corrigir os CDOs).

Colunas da BASE_APONTAMENTOS (cabeçalho na linha 3, dados a partir da 4):
  A DATA | B CR | C SUPERVISOR | D ENCARREGADO
  E APONTOU NO PRAZO?        CDO criado no mesmo dia do boletim (horário de MS)
  F APONTOU NO APP?          quem cadastrou o CDO é o próprio encarregado
  G HORA HOMEM/HORA MÁQUINA  sem R1 (100% por função), R2 (motorista sem veículo) e R5 (máquinas x produção)
  H APONTAMENTO DE PRODUÇÃO  sem R7 (hora trabalhada com produção zerada)
  I TODOS COLABORADORES      sem R3        J TODOS EQUIPAMENTOS  sem R4
  K HORÍMETROS CORRETOS      sem R6
  L QTD ERROS | M PONTOS DESCONTADOS (fórmulas da planilha) | N OBSERVAÇÕES
"""
import os
from datetime import datetime, timedelta
from urllib.parse import quote

from correcao_cdo import norm

SHEET_ID = os.environ.get("RANKING_SHEET_ID", "1u8OD67yFx8syUHvBh-saZmCes39nioT0263ynDqVAVI")
ABA = "BASE_APONTAMENTOS"
PRIMEIRA = 4
FUSO_MS = timedelta(hours=-4)
CR_POR_CONTRATO = {"lacan": 1270, "arauco": 1400, "ms florestal": 1410, "innovatech": 1420,
                   "colpar": 1421, "eucatex": 1430}
TURMAS_FORA = ("apoio e manut", "administrativo")       # turmas de apoio não entram no ranking
NOME_REGRA = {"R1": "horas por função fora de 100%", "R2": "motorista sem veículo com hora trabalhada",
              "R3": "colaborador da turma não lançado", "R4": "equipamento da turma não apontado",
              "R5": "máquinas x produção", "R6": "horímetro", "R7": "produção zerada"}
COLUNA = {"G": ("R1", "R2", "R5"), "H": ("R7",), "I": ("R3",), "J": ("R4",), "K": ("R6",)}


def serial(iso):
    return (datetime.strptime(iso, "%Y-%m-%d") - datetime(1899, 12, 30)).days


def data_local(iso_utc):
    """'2026-11-13T01:49:56.973Z' -> '2026-11-12' (MS, UTC-4). Vazio se não der para ler."""
    try:
        return (datetime.strptime(iso_utc[:19], "%Y-%m-%dT%H:%M:%S") + FUSO_MS).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def cr_de(c):
    digitos = "".join(ch for ch in str(c.get("cr") or "") if ch.isdigit())
    if len(digitos) == 4:
        return int(digitos)
    return CR_POR_CONTRATO.get(norm(c.get("contrato")), "")


def montar(todos):
    """Resumo por CDO (detectar()['todos']) -> linhas do ranking, uma por (data, encarregado)."""
    grupos, sem_nota = {}, []
    for c in todos:
        if not c.get("encarregado") or any(norm(c.get("turma")).startswith(t) for t in TURMAS_FORA):
            continue
        if not c.get("cadastro_ok"):
            sem_nota.append(f"CDO {c['cdo']} ({c['encarregado']}): cadastro da turma indisponível")
            continue
        g = grupos.setdefault((c["data"], norm(c["encarregado"])), {
            "data": c["data"], "cr": cr_de(c), "supervisor": c.get("supervisor") or "",
            "encarregado": c["encarregado"], "regras": set(), "prazo": True, "app": True, "cdos": []})
        g["regras"] |= set(c.get("regras") or [])
        criado = data_local(c.get("criado_em"))
        if criado and criado != c["data"]:
            g["prazo"] = False
        if c.get("criado_por") and norm(c["criado_por"]) != norm(c["encarregado"]):
            g["app"] = False
        g["cdos"].append(str(c["cdo"]))
    linhas = []
    for g in grupos.values():
        sn = lambda ok: "SIM" if ok else "NÃO"
        resp = {"E": sn(g["prazo"]), "F": sn(g["app"])}
        for col, regras in COLUNA.items():
            resp[col] = sn(not (g["regras"] & set(regras)))
        obs = [NOME_REGRA[r] for r in sorted(g["regras"])]
        if not g["prazo"]:
            obs.insert(0, "CDO criado fora do dia")
        if not g["app"]:
            obs.insert(0, "CDO cadastrado por outra pessoa")
        linhas.append(dict(g, respostas=resp, regras=sorted(g["regras"]),
                           obs=("CDO " + "/".join(g["cdos"]) + (": " + "; ".join(obs) if obs else ""))))
    linhas.sort(key=lambda x: (x["data"], str(x["cr"]), x["encarregado"]))
    return linhas, sem_nota


def casar(nome, existentes):
    """Usa a grafia que já está na planilha (ex.: 'RENILDO DA CONCEIÇÃO OLIVEIRA') para o mesmo
    encarregado não aparecer duas vezes no ranking. existentes: {nome normalizado: grafia}."""
    n = norm(nome)
    if n in existentes:
        return existentes[n]
    perto = [v for k, v in existentes.items() if k and (k.startswith(n) or n.startswith(k))]
    return perto[0] if len(perto) == 1 else str(nome).upper()


def gravar(base, linhas, log=print):
    """Acrescenta no fim da BASE_APONTAMENTOS as linhas cujo (data, encarregado) ainda não existe."""
    atual = base.valores([f"{ABA}!A{PRIMEIRA}:D5000"])[0]
    while atual and not (len(atual[-1]) > 3 and str(atual[-1][3]).strip()):
        atual.pop()
    enc, sup, chaves = {}, {}, set()
    for r in atual:
        r = list(r) + [""] * (4 - len(r))
        if str(r[3]).strip():
            enc.setdefault(norm(r[3]), str(r[3]).strip())
            try:
                chaves.add((int(float(r[0])), norm(r[3])))
            except (TypeError, ValueError):
                pass
        if str(r[2]).strip():
            sup.setdefault(norm(r[2]), str(r[2]).strip())
    novas, ja = [], 0
    for x in linhas:
        nome = casar(x["encarregado"], enc)
        k = (serial(x["data"]), norm(nome))
        if k in chaves:
            ja += 1
            continue
        chaves.add(k)
        novas.append((x, nome))
    if not novas:
        log(f"  Ranking: nada novo a gravar ({ja} linha(s) já existiam).")
        return {"gravadas": 0, "ja_existiam": ja}
    ini = PRIMEIRA + len(atual)
    fim = ini + len(novas) - 1
    folha = next(s["properties"] for s in base.meta()["sheets"] if s["properties"]["title"] == ABA)
    falta = fim + 50 - folha["gridProperties"]["rowCount"]
    if falta > 0:
        base.batch([{"appendDimension": {"sheetId": folha["sheetId"], "dimension": "ROWS", "length": falta}}])
    valores = []
    for i, (x, nome) in enumerate(novas):
        n = ini + i
        r = x["respostas"]
        valores.append([serial(x["data"]), x["cr"], casar(x["supervisor"], sup), nome,
                        r["E"], r["F"], r["G"], r["H"], r["I"], r["J"], r["K"],
                        f'=IF(D{n}="";0;COUNTIF(E{n}:K{n};"NÃO"))',
                        f'=IF(D{n}="";0;COUNTIF(E{n}:K{n};"NÃO")*10)', x["obs"]])
    base._req("PUT", "/values/" + quote(f"{ABA}!A{ini}:N{fim}"),
              params={"valueInputOption": "USER_ENTERED"}, json={"values": valores})
    base.batch([{"repeatCell": {
        "range": {"sheetId": folha["sheetId"], "startRowIndex": ini - 1, "endRowIndex": fim,
                  "startColumnIndex": 0, "endColumnIndex": 1},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}},
        "fields": "userEnteredFormat.numberFormat"}}])
    log(f"  Ranking: {len(novas)} linha(s) gravada(s) na {ABA} (linhas {ini} a {fim}); {ja} já existiam.")
    return {"gravadas": len(novas), "ja_existiam": ja, "linha_inicial": ini, "linha_final": fim}


def registrar(base, deteccao, log=print):
    linhas, sem_nota = montar(deteccao.get("todos") or [])
    res = gravar(base, linhas, log)
    res["sem_nota"] = sem_nota
    res["com_erro"] = sum(1 for x in linhas if "NÃO" in x["respostas"].values())
    res["avaliados"] = len(linhas)
    return res
