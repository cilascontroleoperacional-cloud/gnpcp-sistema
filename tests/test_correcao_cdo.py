"""Testes da correção de CDO com uma API simulada que reproduz o CDO 53489 (12/11/2026, LACAN,
turma do Renildo) com os dados reais lidos do ProdControl em 13/11/2026."""
import copy, os, sys
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import correcao_cdo as cc

CDO, CDO_ANT = "56bfe264-7953-4b1b-976a-310f1dc26b68", "9f25f9a6-2d50-4621-bc21-43666b510bc1"
LACAN = [{"nome": "LACAN", "contractId": "5a5763bf-e84c-4027-831e-9f2c5e4a4f76"}]
RT = {"mot": "b4e33ebf-79f7-435c-ac82-84f1e391e705", "pesada": "rt-37", "pneu": "rt-17", "tf": "rt-1", "enc": "rt-enc"}
PF_APOIO, OP_APOIO = "2b544f41-5963-4581-b361-de3e3a18743c", "9394f2b8-2648-4c47-817a-d7336f9d37c1"
OPS = {"39": "PREPARO DE SOLO MECÂNICO COM FOSFATAGEM + NPK + COVEAMENTO", "110": "GRADAGEM NA ENTRE LINHA",
       "02-x": "APOIO E MANUTEÇÃO"}
PAYLOAD_REAL = {  # exatamente o que o site enviou em 13/11/2026 (DevTools)
    "id": "289076d3-b3e5-4910-b8eb-327835ea502d", "operationDailyControlId": CDO, "operationId": OP_APOIO,
    "plotId": "df01cc5b-9870-4bd4-82f1-3a2ae895e867", "priceFormationId": PF_APOIO, "productiveAmount": 0,
    "projectId": "53c9e8d8-4871-4523-b287-85d5b15760d6", "resourceTypeId": RT["mot"],
    "statusId": "4c73fe9b-0caa-470b-be9a-5b38f8b080a5", "totalEmployees": 1, "unproductiveHours": 8, "workedHours": 0}


def prod(i, rt, nome, op, talhao, ht, hi, q="0.00", com_op_id=True):
    pf = PF_APOIO if op == "02-x" else "pf-" + op
    operacao = {"name": OPS[op], "code": op}
    if com_op_id:
        operacao["id"] = OP_APOIO if op == "02-x" else "op-" + op
    return {"id": i, "operationDailyControl": {"id": CDO}, "workedHours": ht, "unproductiveHours": hi,
            "productiveAmount": q, "totalEmployees": 1, "resourceType": {"id": rt, "name": nome, "code": 1},
            "priceFormation": {"id": pf, "operation": operacao},
            "project": {"id": "53c9e8d8-4871-4523-b287-85d5b15760d6", "name": "TRÊS BARRAS"},
            "plot": {"id": "df01cc5b-9870-4bd4-82f1-3a2ae895e867", "name": talhao},
            "status": {"id": "4c73fe9b-0caa-470b-be9a-5b38f8b080a5", "name": "CONCLUIDO"}}


def worker(nome, rt, func, tipo, j):
    return {"id": "w-" + nome, "dailyJourney": j, "operationDailyControl": {"id": CDO},
            "employee": {"id": "e-" + nome, "name": nome, "employeeNumber": "1", "resourceType": {"id": rt, "name": func}},
            "type": {"id": "t-" + tipo, "name": tipo}}


def maq(cod, tipo, op, talhao, ht="0.00", ini="0.00", fim="0.00", paradas=(), odc=CDO):
    # na lista do CDO o tipo do patrimônio vem sem a categoria; ela sai do cadastro da turma
    return {"id": f"m-{cod}-{talhao}-{odc[:4]}", "operationDailyControl": {"id": odc}, "workedHours": ht,
            "hourMeterStart": ini, "hourMeterEnd": fim,
            "asset": {"id": "a-" + cod, "code": cod, "resourceType": {"name": tipo}},
            "priceFormation": {"id": "pf-" + op, "operation": {"code": op, "name": OPS[op]}},
            "plot": {"name": talhao},
            "odcMachineStoppages": [{"time": h, "workStoppage": {"type": {"name": tp}}} for tp, h in paradas]}


def ativo(cod, tipo, cat):
    return {"id": "a-" + cod, "code": cod, "resourceType": {"name": tipo, "type": {"name": cat}}}


def colab(nome, func):
    return {"id": "e-" + nome, "name": nome, "employeeNumber": "1", "resourceType": {"name": func}}


class Fake:
    """Imita ProdControlAPI.get/put. Valores numéricos vêm como texto, como na API real.
    Estado padrão = CDO como o encarregado deixou nas horas de gente (Cleiton de Folga, motorista com
    8 h trabalhadas) e com a aba MÁQUINAS já certa. Os parâmetros ligam cada situação."""
    def __init__(self, cleiton_presente=False, com_ismael=True, com_caminhao=False, com_op_id=True,
                 gntp282_errada=False):
        self.puts, self.falhar_put, self.cadastro_fora = [], False, False
        self.cab = {"id": CDO, "code": 53489, "bulletinDate": "2026-11-12",
                    "leader": {"name": "RENILDO DA CONCEICAO OLIVEIRA"}, "supervisor": {"name": "ADRIANO BARROS DA COSTA"},
                    "class": {"id": "265f5c6b", "name": "RENILDO DA CONCEICAO OLIVEIRA", "costCenter": {"name": "GN1270"}},
                    "createdBy": {"name": "Renildo da Conceição Oliveira"}, "createdAt": "2026-11-13T01:49:56.973Z"}
        self.cab_ant = {"id": CDO_ANT, "code": 53437, "bulletinDate": "2026-11-11", "class": {"id": "265f5c6b"}}
        self.prod = [
            prod("p1", RT["pesada"], "Operador de Máquina Pesada", "39", "1", "1.00", "6.00", "1.82"),
            prod("p2", RT["pesada"], "Operador de Máquina Pesada", "39", "2", "1.00", "0.00", "3.18"),
            prod("p3", RT["tf"], "Trabalhador Florestal", "02-x", "2", "9.00", "0.00"),
            prod(PAYLOAD_REAL["id"], RT["mot"], "Motorista", "02-x", "2", "8.00", "0.00", com_op_id=com_op_id),
            prod("p5", RT["pneu"], "Operador de Trator de Pneu", "110", "13", "3.00", "0.00", "6.58"),
            prod("p6", RT["pneu"], "Operador de Trator de Pneu", "110", "14", "3.00", "0.00", "6.58"),
            prod("p7", RT["pneu"], "Operador de Trator de Pneu", "110", "15", "1.00", "0.00", "3.20"),
            prod("p8", RT["pneu"], "Operador de Trator de Pneu", "110", "16", "1.00", "0.00", "3.20")]
        self.mdo = [worker("ROSIVALDO", RT["tf"], "Trabalhador Florestal", "Presente", "9.00"),
                    worker("RENILDO", RT["enc"], "Encarregado Operacional", "Presente", "8.00"),
                    worker("JOAO", RT["mot"], "Motorista", "Presente", "8.00"),
                    worker("GABRIEL", RT["pesada"], "Operador de Máquinas Pleno", "Presente", "8.00"),
                    worker("CLEITON", RT["pesada"], "Operador de Máquinas Pleno",
                           "Presente" if cleiton_presente else "Folga", "8.00")]
        if com_ismael:      # veio de outra turma: está na MÃO DE OBRA, mas não no cadastro da turma
            self.mdo.append(worker("ISMAEL", RT["pneu"], "Operador de Trator de Pneu", "Presente", "8.00"))
        g1 = (maq("GNTP282", "Trator de Pneu Pesado", "39", "1", "8.00", "3062.00", "3070.00") if gntp282_errada else
              maq("GNTP282", "Trator de Pneu Pesado", "39", "1", "1.00", "3065.00", "3066.00", [("Operacionais", "6.00")]))
        self.maq = [
            maq("TP276", "Trator de Pneu Leve", "02-x", "1", "0.00", "11294.00", "11294.00", [("Mecânicas", "8.00")]),
            maq("GH37", "Grade Hidráulica", "110", "15", "1.00"), maq("GH37", "Grade Hidráulica", "110", "16", "1.00"),
            maq("GH37", "Grade Hidráulica", "110", "13", "3.00"), maq("GH37", "Grade Hidráulica", "110", "14", "3.00"),
            maq("GNTP302", "Trator de Pneu Leve", "110", "15", "1.00", "2025.00", "2026.00"),
            maq("GNTP302", "Trator de Pneu Leve", "110", "16", "1.00", "2024.00", "2025.00"),
            maq("GNTP302", "Trator de Pneu Leve", "110", "13", "3.00", "2029.00", "2032.00"),
            maq("GNTP302", "Trator de Pneu Leve", "110", "14", "3.00", "2026.00", "2029.00"),
            g1, maq("GNTP282", "Trator de Pneu Pesado", "39", "2", "1.00", "3064.00", "3065.00"),
            maq("GNSS26", "Subsolador", "39", "1", "1.00", paradas=[("Operacionais", "6.00")]),
            maq("GNSS26", "Subsolador", "39", "2", "1.00")]
        self.maq_ant = [      # CDO 53437 de 11/11/2026 (dia anterior da mesma turma)
            maq("GNTP282", "Trator de Pneu Pesado", "39", "2", "6.00", "3058.00", "3064.00", [("Operacionais", "2.00")], CDO_ANT),
            maq("GNTP302", "Trator de Pneu Leve", "110", "13", "0.00", "2024.00", "2024.00", [("Mecânicas", "8.00")], CDO_ANT),
            maq("TP276", "Trator de Pneu Leve", "02-x", "2", "0.00", "11294.00", "11294.00", [("Mecânicas", "8.00")], CDO_ANT)]
        # cadastro real da turma em 12/11/2026 (lido do ProdControl)
        self.ativos = [ativo("TP276", "Trator de Pneu Leve", "Máquinas"), ativo("GNSS26", "Subsolador", "Implementos"),
                       ativo("GNTP302", "Trator de Pneu Leve", "Máquinas"), ativo("GNTP282", "Trator de Pneu Pesado", "Máquinas"),
                       ativo("GH37", "Grade Hidráulica", "Implementos")]
        self.colabs = [colab("GABRIEL", "Operador de Máquinas Pleno"), colab("JOAO", "Motorista"),
                       colab("RENILDO", "Encarregado Operacional"), colab("ROSIVALDO", "Trabalhador Florestal"),
                       colab("CLEITON", "Operador de Máquinas Pleno")]
        if com_caminhao:
            self.ativos.append(ativo("CM01", "Caminhão Comboio", "Veículos"))
            self.maq.append(maq("CM01", "Caminhão Comboio", "02-x", "2", "8.00", "500.00", "508.00"))

    def get(self, path):
        u = urlparse(path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        pag = lambda itens: {"items": copy.deepcopy(itens), "meta": {"totalPages": 1}}
        if u.path in ("/odc", "/odc/machine"):
            assert q["endDate"] == "2026-11-12" and q["startDate"] == "2026-11-02"      # 10 dias para trás
            return pag([self.cab, self.cab_ant] if u.path == "/odc" else self.maq + self.maq_ant)
        if u.path == "/odc/production":
            assert "startDate" not in q or q["startDate"] == "2026-11-12"
            return pag(self.prod)
        if u.path == "/odc/worker":
            assert q["operationDailyControlId"] == CDO
            return pag(self.mdo)
        if u.path in ("/employees", "/assets"):
            if self.cadastro_fora:
                raise RuntimeError("500")
            assert q["date"] == "12/11/2026" and q["contractId"] == LACAN[0]["contractId"] and q["deletedAt"] == "false"
            assert q.get("classId" if u.path == "/employees" else "class") == "265f5c6b"
            return pag(self.colabs if u.path == "/employees" else self.ativos)
        if u.path.startswith("/assets/"):
            if self.cadastro_fora:
                raise RuntimeError("500")
            return next(copy.deepcopy(x) for x in self.ativos + [ativo("EXTRA1", "Trator de Esteira", "Máquinas")] if x["id"] == u.path.split("/")[-1])
        if u.path == f"/prices-formation/{PF_APOIO}":
            return {"id": PF_APOIO, "operation": {"id": OP_APOIO, "name": "APOIO E MANUTEÇÃO"}}
        raise AssertionError("rota inesperada: " + path)

    def put(self, path, body):
        if self.falhar_put:
            raise RuntimeError("504 timeout")
        self.puts.append((path, body))
        linha = next(p for p in self.prod if p["id"] == body["id"])
        linha["workedHours"], linha["unproductiveHours"] = f"{body['workedHours']:.2f}", f"{body['unproductiveHours']:.2f}"
        return copy.deepcopy(linha)


def det(api):
    return cc.detectar(api, LACAN, "2026-11-12", "2026-11-12", log=lambda m: None)


def achados(d):
    return [x for a in d["cdos"] for x in a["achados"]]


def por_regra(d):
    return {x["regra"] + ":" + x["grupo"]: x for x in achados(d)}


def corrigido():
    """CDO depois das correções de 13/11: Cleiton Presente e motorista em horas improdutivas."""
    api = Fake(cleiton_presente=True)
    api.prod[3]["workedHours"], api.prod[3]["unproductiveHours"] = "0.00", "8.00"
    return api


def test_cdo_53489_como_o_encarregado_deixou():
    d = det(Fake())
    xs = por_regra(d)
    assert set(xs) == {"R1:OPERADORES", "R2:MOTORISTAS"}          # TF 9x9 e motorista 8x8 fecham
    op = xs["R1:OPERADORES"]
    # como no painel: só Gabriel conta como presente (Cleiton de folga; Ismael é de outra turma)
    assert (op["horas_apontadas"], op["horas_presentes"], op["diferenca"]) == (16.0, 8.0, 8.0)
    assert "200%" in op["titulo"] and "CLEITON" in op["deducao"][0] and "ISMAEL" in op["deducao"][-1]
    r2 = xs["R2:MOTORISTAS"]
    assert r2["tipo"] == "corrigir" and r2["rota"] == "/odc/production/" + PAYLOAD_REAL["id"]
    assert r2["corpo"] == PAYLOAD_REAL                             # idêntico ao que o site enviou
    assert d["resumo"]["corrigir"] == 1 and d["resumo"]["revisar"] == 1
    assert d["todos"] == [{"cdo": 53489, "data": "2026-11-12", "contrato": "LACAN",
                           "encarregado": "RENILDO DA CONCEICAO OLIVEIRA", "supervisor": "ADRIANO BARROS DA COSTA",
                           "turma": "RENILDO DA CONCEICAO OLIVEIRA", "criado_por": "Renildo da Conceição Oliveira",
                           "criado_em": "2026-11-13T01:49:56.973Z", "cr": "GN1270", "cadastro_ok": True,
                           "regras": ["R1", "R2"]}]


def test_cdo_corrigido_fecha_tudo_como_no_painel():
    d = det(corrigido())                                           # painel: Operadores 16 x 16, Máquinas 10 x 10
    assert achados(d) == [] and d["cdos"] == [] and d["todos"][0]["regras"] == []


def test_aplicar_grava_so_o_aprovado():
    api = Fake(cleiton_presente=True)
    d = det(api)
    assert [x["regra"] for x in achados(d)] == ["R2"]
    ids = [x["id"] for x in achados(d)]
    r = cc.aplicar(api, d, ids + ["nao-existe"], log=lambda m: None)
    assert r["aplicados"] == 1 and len(api.puts) == 1 and api.puts[0][1] == PAYLOAD_REAL
    assert r["itens"][0]["antes"] == {"workedHours": 8.0, "unproductiveHours": 0.0}
    assert r["itens"][0]["depois"] == {"workedHours": 0.0, "unproductiveHours": 8.0}
    assert r["itens"][1]["situacao"] == "ignorado"
    assert achados(det(api)) == []                                 # CDO todo em 100%
    r = cc.aplicar(api, d, ids, log=lambda m: None)                # repetir não grava de novo
    assert r["aplicados"] == 0 and r["itens"][0]["situacao"] == "pulado" and len(api.puts) == 1


def test_maquina_diferente_da_producao_aponta_a_linha_e_a_correcao():
    api = corrigido()
    api.maq = Fake(gntp282_errada=True).maq                        # GNTP282 talhão 1: 8 h, sem parada, 3.062 → 3.070
    xs = por_regra(det(api))
    assert set(xs) == {"R5:MÁQUINAS", "R6:HORÍMETRO"}              # implementos e TP276 parado não são erro
    r5 = xs["R5:MÁQUINAS"]
    assert len(r5["deducao"]) == 1 and r5["itens"] == [{"onde": "39 talhão 1", "equipamentos": ["GNTP282"],
                                                        "maquina": [8.0, 0.0], "producao": [1.0, 6.0]}]
    assert r5["deducao"][0] == ("GNTP282 (39 talhão 1): 8 h trabalhadas e 0 h paradas; na PRODUÇÃO são 1 h "
                                "trabalhadas e 6 h improdutivas. Ajustar a aba MÁQUINAS para 1 h trabalhadas e "
                                "6 h de paralisação.")
    r6 = xs["R6:HORÍMETRO"]["deducao"]
    assert r6 == ["GNTP282: linha do talhão 2 começa em 3.064, mas a anterior (talhão 1) terminou em 3.070.",
                  "GNTP282: o dia começa em 3.062, mas o último horímetro apontado foi 3.064 (CDO 53437 de 11/11)."]


def test_horimetro_diferente_das_horas_da_linha():
    api = corrigido()
    g = next(m for m in api.maq if m["asset"]["code"] == "GNTP282" and m["plot"]["name"] == "1")
    g["hourMeterStart"], g["hourMeterEnd"] = "3062.00", "3070.00"  # como ficou depois da 1ª correção (só horas)
    r6 = por_regra(det(api))["R6:HORÍMETRO"]["deducao"]
    assert r6[0] == "GNTP282 (talhão 1): horímetro 3.062 → 3.070 = 8 h, mas a linha tem 1 h trabalhadas."
    assert len(r6) == 3


def test_item_de_revisao_nunca_e_gravado():
    api = Fake(); d = det(api)
    rev = [x["id"] for x in achados(d) if x["tipo"] == "revisar"]
    r = cc.aplicar(api, d, rev, log=lambda m: None)
    assert r["aplicados"] == 0 and api.puts == []


def test_com_caminhao_motorista_fica_como_esta():
    assert achados(det(Fake(cleiton_presente=True, com_caminhao=True))) == []


def test_caminhao_no_cadastro_sem_apontar():
    api = Fake(cleiton_presente=True, com_caminhao=True)
    api.maq = [m for m in api.maq if m["asset"]["code"] != "CM01"]
    xs = por_regra(det(api))
    assert set(xs) == {"R4:EQUIPAMENTOS", "R5:VEÍCULOS"}            # NÃO oferece passar motorista p/ improdutiva
    assert "CM01" in xs["R4:EQUIPAMENTOS"]["deducao"][0]
    assert xs["R5:VEÍCULOS"]["deducao"][0] == "Horas trabalhadas: VEÍCULOS 0 h x MOTORISTAS 8 h."


def test_colaborador_e_maquina_da_turma_nao_lancados():
    api = corrigido()
    api.mdo = [w for w in api.mdo if w["employee"]["name"] != "RENILDO"]
    api.maq = [m for m in api.maq if m["asset"]["code"] != "GNTP302"]
    xs = por_regra(det(api))
    assert set(xs) == {"R3:MÃO DE OBRA", "R4:EQUIPAMENTOS", "R5:MÁQUINAS"}
    assert "RENILDO" in xs["R3:MÃO DE OBRA"]["deducao"][0] and "GNTP302" in xs["R4:EQUIPAMENTOS"]["deducao"][0]
    assert len(xs["R5:MÁQUINAS"]["deducao"]) == 4 and "110 talhão 13: operadores com 3 h" in xs["R5:MÁQUINAS"]["deducao"][0]


def test_operador_sem_as_horas_paradas_da_maquina():
    api = corrigido()
    api.prod[0]["unproductiveHours"] = "0.00"                      # operador sem as 6 h improdutivas do talhão 1
    xs = por_regra(det(api))
    assert set(xs) == {"R1:OPERADORES", "R5:MÁQUINAS", "R5:IMPLEMENTOS"}
    assert "GNTP282 (39 talhão 1): 1 h trabalhadas e 6 h paradas; na PRODUÇÃO são 1 h trabalhadas e 0 h" in xs["R5:MÁQUINAS"]["deducao"][0]
    assert xs["R5:IMPLEMENTOS"]["itens"][0]["equipamentos"] == ["GNSS26"]


def test_producao_zerada_com_hora_trabalhada():
    api = corrigido()
    api.prod[4]["productiveAmount"] = "0.00"                       # gradagem talhão 13 com 3 h e sem hectare
    xs = por_regra(det(api))
    assert set(xs) == {"R7:PRODUÇÃO"} and "110 talhão 13" in xs["R7:PRODUÇÃO"]["deducao"][0]   # apoio (02-x) não conta


def test_sem_cadastro_nao_corrige_sozinho():
    api = Fake(cleiton_presente=True); api.cadastro_fora = True
    d = det(api)
    assert d["cdos"][0]["avisos"] and d["resumo"]["cdos_sem_cadastro"] == 1 and d["todos"][0]["cadastro_ok"] is False
    xs = achados(d)
    # sem cadastro: todos da MÃO DE OBRA contam (Ismael entra: 24 x 16) e a R2 vira só revisão
    assert [(x["regra"], x["tipo"]) for x in xs] == [("R1", "revisar"), ("R2", "revisar")] and "corpo" not in xs[1]
    assert any("categoria desconhecida" in a for a in d["cdos"][0]["avisos"])
    assert cc.aplicar(api, d, [xs[1]["id"]], log=lambda m: None)["aplicados"] == 0 and api.puts == []


def test_maquina_emprestada_de_outra_turma_e_classificada_pelo_patrimonio():
    api = corrigido()
    api.maq.append(maq("EXTRA1", "Trator de Esteira", "02-x", "2", "0.00", "100.00", "100.00", [("Mecânicas", "4.00")]))
    d = det(api)
    assert achados(d) == [] and d["cdos"] == []


def test_operacao_resolvida_pela_formacao_de_preco():
    x = achados(det(Fake(cleiton_presente=True, com_op_id=False)))[0]
    assert x["tipo"] == "corrigir" and x["corpo"] == PAYLOAD_REAL


def test_put_que_falha_nao_e_repetido():
    api = Fake(cleiton_presente=True); d = det(api); api.falhar_put = True
    r = cc.aplicar(api, d, [achados(d)[0]["id"]], log=lambda m: None)
    assert r["itens"][0]["situacao"] == "conferir" and api.puts == []


def test_falta_apontar_e_grupo_sem_mao_de_obra():
    api = corrigido()
    api.prod = [p for p in api.prod if p["id"] != "p3"]            # TF presente 9 h, nada apontado
    api.mdo = [w for w in api.mdo if w["employee"]["name"] != "JOAO"]   # motorista apontado sem estar na MDO
    xs = por_regra(det(api))
    assert xs["R1:TRABALHADORES FLORESTAIS"]["diferenca"] == -9.0 and "Faltam 9 h" in xs["R1:TRABALHADORES FLORESTAIS"]["deducao"][0]
    assert xs["R1:MOTORISTAS"]["horas_presentes"] == 0 and "Nenhum colaborador" in xs["R1:MOTORISTAS"]["deducao"][0]
    assert "R3:MÃO DE OBRA" in xs


def test_utilitarios():
    assert cc.num("1.234,50") == 1234.5 and cc.num("8.00") == 8.0 and cc.num(None) == 0
    assert cc.fmt(3065) == "3.065" and cc.fmt(6.58) == "6,58" and cc.fmt(11294.5) == "11.294,5" and cc.fmt(0) == "0"
    assert cc.eh_veiculo("Caminhão Pipa") and cc.eh_veiculo("Ônibus") and not cc.eh_veiculo("Veículo Leve")
    assert not cc.eh_veiculo("Trator de Pneu") and not cc.eh_veiculo("Escavadeira")
    assert cc.grupo_funcao("Operador de Máquinas Pleno") == "OPERADORES" and cc.grupo_funcao("Encarregado Operacional") is None
    c = lambda n, t=None: cc.categoria_equip({"name": n, "type": {"name": t}})
    assert c("Trator de Pneu Leve", "Máquinas") == "MAQUINAS" and c("Subsolador", "Implementos") == "IMPLEMENTOS"
    assert c("Caminhão Pipa", "Veículos") == "VEICULOS" and c("Veículo Leve", "Veículos") == "VL"
    assert c("Ônibus") == "VEICULOS" and c("Trator de Pneu Leve") == "MAQUINAS"
