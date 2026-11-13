"""Testes da correção de CDO com uma API simulada que reproduz o CDO 53489 (12/11/2026, LACAN)."""
import copy, os, sys
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import correcao_cdo as cc

CDO = "56bfe264-7953-4b1b-976a-310f1dc26b68"
LACAN = [{"nome": "LACAN", "contractId": "5a5763bf-e84c-4027-831e-9f2c5e4a4f76"}]
RT = {"mot": "b4e33ebf-79f7-435c-ac82-84f1e391e705", "pesada": "rt-37", "pneu": "rt-17", "tf": "rt-1", "enc": "rt-enc"}
PF_APOIO, OP_APOIO = "2b544f41-5963-4581-b361-de3e3a18743c", "9394f2b8-2648-4c47-817a-d7336f9d37c1"
PAYLOAD_REAL = {  # exatamente o que o site enviou em 13/11/2026 (DevTools)
    "id": "289076d3-b3e5-4910-b8eb-327835ea502d", "operationDailyControlId": CDO, "operationId": OP_APOIO,
    "plotId": "df01cc5b-9870-4bd4-82f1-3a2ae895e867", "priceFormationId": PF_APOIO, "productiveAmount": 0,
    "projectId": "53c9e8d8-4871-4523-b287-85d5b15760d6", "resourceTypeId": RT["mot"],
    "statusId": "4c73fe9b-0caa-470b-be9a-5b38f8b080a5", "totalEmployees": 1, "unproductiveHours": 8, "workedHours": 0}


def prod(i, rt, nome, op, talhao, ht, hi, q=0, pf="pf-x", com_op_id=True):
    operacao = {"name": op, "code": "x"}
    if com_op_id:
        operacao["id"] = OP_APOIO if pf == PF_APOIO else "op-" + op[:4]
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


def maq(cod, tipo, ht="0.00", paradas=()):
    # na lista do CDO o tipo do patrimônio vem sem a categoria; ela sai do cadastro da turma
    return {"id": "m-" + cod, "operationDailyControl": {"id": CDO}, "workedHours": ht,
            "asset": {"id": "a-" + cod, "code": cod, "resourceType": {"name": tipo}},
            "odcMachineStoppages": [{"time": h, "workStoppage": {"type": {"name": tp}}} for tp, h in paradas]}


def ativo(cod, tipo, cat):
    return {"id": "a-" + cod, "code": cod, "resourceType": {"name": tipo, "type": {"name": cat}}}


def colab(nome, func):
    return {"id": "e-" + nome, "name": nome, "employeeNumber": "1", "resourceType": {"name": func}}


class Fake:
    """Imita ProdControlAPI.get/put. Valores numéricos vêm como texto, como na API real."""
    def __init__(self, com_ismael=False, com_caminhao=False, com_op_id=True):
        self.puts, self.falhar_put = [], False
        self.prod = [
            prod("p1", RT["pesada"], "Operador de Máquina Pesada", "PREPARO DE SOLO", "1", "1.00", "6.00", "1.82"),
            prod("p2", RT["pesada"], "Operador de Máquina Pesada", "PREPARO DE SOLO", "2", "1.00", "0.00", "3.18"),
            prod("p3", RT["tf"], "Trabalhador Florestal", "APOIO E MANUTEÇÃO", "2", "9.00", "0.00", pf=PF_APOIO),
            prod(PAYLOAD_REAL["id"], RT["mot"], "Motorista", "APOIO E MANUTEÇÃO", "2", "8.00", "0.00", pf=PF_APOIO, com_op_id=com_op_id),
            prod("p5", RT["pneu"], "Operador de Trator de Pneu", "GRADAGEM", "13", "3.00", "0.00", "6.58"),
            prod("p6", RT["pneu"], "Operador de Trator de Pneu", "GRADAGEM", "14", "3.00", "0.00", "6.58"),
            prod("p7", RT["pneu"], "Operador de Trator de Pneu", "GRADAGEM", "15", "1.00", "0.00", "3.20"),
            prod("p8", RT["pneu"], "Operador de Trator de Pneu", "GRADAGEM", "16", "1.00", "0.00", "3.20")]
        self.mdo = [worker("ROSIVALDO", RT["tf"], "Trabalhador Florestal", "Presente", "9.00"),
                    worker("RENILDO", RT["enc"], "Encarregado Operacional", "Presente", "8.00"),
                    worker("JOAO", RT["mot"], "Motorista", "Presente", "8.00"),
                    worker("GABRIEL", RT["pesada"], "Operador de Máquinas Pleno", "Presente", "8.00"),
                    worker("CLEITON", RT["pesada"], "Operador de Máquinas Pleno", "Folga", "8.00")]
        if com_ismael:
            self.mdo.append(worker("ISMAEL", RT["pneu"], "Operador de Trator de Pneu", "Presente", "8.00"))
        self.maq = [maq("GNTP282", "Trator de Pneu Pesado", "2.00", [("Operacionais", "6.00")]),
                    maq("GNTP302", "Trator de Pneu Leve", "8.00"),
                    maq("TP276", "Trator de Pneu Leve", "0.00", [("Mecânicas", "8.00")]),
                    maq("GH37", "Grade Hidráulica", "8.00"),
                    maq("GNSS26", "Subsolador", "2.00", [("Operacionais", "6.00")])]
        # cadastro real da turma em 12/11/2026 (lido do ProdControl)
        self.ativos = [ativo("TP276", "Trator de Pneu Leve", "Máquinas"), ativo("GNSS26", "Subsolador", "Implementos"),
                       ativo("GNTP302", "Trator de Pneu Leve", "Máquinas"), ativo("GNTP282", "Trator de Pneu Pesado", "Máquinas"),
                       ativo("GH37", "Grade Hidráulica", "Implementos")]
        self.colabs = [colab("GABRIEL", "Operador de Máquinas Pleno"), colab("JOAO", "Motorista"),
                       colab("RENILDO", "Encarregado Operacional"), colab("ROSIVALDO", "Trabalhador Florestal"),
                       colab("CLEITON", "Operador de Máquinas Pleno")]
        self.cadastro_fora = False
        if com_caminhao:
            self.ativos.append(ativo("CM01", "Caminhão Comboio", "Veículos"))
            self.maq.append(maq("CM01", "Caminhão Comboio", "8.00"))

    def get(self, path):
        u = urlparse(path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        pag = lambda itens: {"items": copy.deepcopy(itens), "meta": {"totalPages": 1}}
        if u.path == "/odc":
            assert q["startDate"] == q["endDate"] == "2026-11-12"
            return pag([{"id": CDO, "code": 53489, "bulletinDate": "2026-11-12", "leader": {"name": "RENILDO"},
                         "class": {"id": "265f5c6b", "name": "T1"}}])
        if u.path == "/odc/machine":
            return pag(self.maq)
        if u.path == "/odc/production":
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


def test_cdo_53489_como_estava():
    d = det(Fake())
    xs = {x["regra"] + ":" + x["grupo"]: x for x in achados(d)}
    assert set(xs) == {"R1:OPERADORES", "R2:MOTORISTAS"}          # TF 9x9 e motorista 8x8 fecham
    op = xs["R1:OPERADORES"]
    assert (op["horas_apontadas"], op["horas_presentes"], op["diferenca"]) == (16.0, 8.0, 8.0)
    assert "200%" in op["titulo"] and "CLEITON" in op["deducao"][0] and op["tipo"] == "revisar"
    r2 = xs["R2:MOTORISTAS"]
    assert r2["tipo"] == "corrigir" and r2["rota"] == "/odc/production/" + PAYLOAD_REAL["id"]
    assert r2["corpo"] == PAYLOAD_REAL                             # idêntico ao que o site enviou
    assert d["resumo"]["corrigir"] == 1 and d["resumo"]["revisar"] == 1


def test_aplicar_grava_so_o_aprovado_e_depois_fecha_100():
    api = Fake(com_ismael=True)
    d = det(api)
    assert [x["regra"] for x in achados(d)] == ["R2"]              # com o Ismael, operadores 16x16
    ids = [x["id"] for x in achados(d)]
    r = cc.aplicar(api, d, ids + ["nao-existe"], log=lambda m: None)
    assert r["aplicados"] == 1 and len(api.puts) == 1 and api.puts[0][1] == PAYLOAD_REAL
    assert r["itens"][0]["antes"] == {"workedHours": 8.0, "unproductiveHours": 0.0}
    assert r["itens"][0]["depois"] == {"workedHours": 0.0, "unproductiveHours": 8.0}
    assert r["itens"][1]["situacao"] == "ignorado"
    assert achados(det(api)) == []                                 # CDO todo em 100%
    r = cc.aplicar(api, d, ids, log=lambda m: None)                # repetir não grava de novo
    assert r["aplicados"] == 0 and r["itens"][0]["situacao"] == "pulado" and len(api.puts) == 1


def test_item_de_revisao_nunca_e_gravado():
    api = Fake(); d = det(api)
    rev = [x["id"] for x in achados(d) if x["tipo"] == "revisar"]
    r = cc.aplicar(api, d, rev, log=lambda m: None)
    assert r["aplicados"] == 0 and api.puts == []


def test_com_caminhao_motorista_fica_como_esta():
    assert [x["regra"] for x in achados(det(Fake(com_ismael=True, com_caminhao=True)))] == []


def test_caminhao_no_cadastro_sem_apontar():
    api = Fake(com_ismael=True, com_caminhao=True)
    api.maq = [m for m in api.maq if m["asset"]["code"] != "CM01"]
    xs = {x["regra"]: x for x in achados(det(api))}
    assert set(xs) == {"R4", "R5"}                                  # NÃO oferece passar motorista p/ improdutiva
    assert "CM01" in xs["R4"]["deducao"][0]
    assert xs["R5"]["grupo"] == "VEÍCULOS" and "VEÍCULOS 0 h x MOTORISTAS 8 h" in xs["R5"]["deducao"][0]


def test_colaborador_e_maquina_da_turma_nao_lancados():
    api = Fake(com_ismael=True)
    api.mdo = [w for w in api.mdo if w["employee"]["name"] != "RENILDO"]
    api.maq = [m for m in api.maq if m["asset"]["code"] != "GNTP302"]
    xs = {x["regra"] + ":" + x["grupo"]: x for x in achados(det(api))}
    assert set(xs) == {"R2:MOTORISTAS", "R3:MÃO DE OBRA", "R4:EQUIPAMENTOS", "R5:MÁQUINAS"}
    assert "RENILDO" in xs["R3:MÃO DE OBRA"]["deducao"][0] and "GNTP302" in xs["R4:EQUIPAMENTOS"]["deducao"][0]
    assert "MÁQUINAS 2 h x OPERADORES 10 h" in xs["R5:MÁQUINAS"]["deducao"][0]


def test_paradas_x_improdutivas():
    api = Fake(com_ismael=True)
    api.prod[0]["unproductiveHours"], api.prod[0]["workedHours"] = "0.00", "1.00"      # operador sem as 6 h paradas
    api.mdo = [w for w in api.mdo]                                                      # R1 também acusa (10 x 16)
    r5 = [x for x in achados(det(api)) if x["regra"] == "R5"]
    assert {x["grupo"] for x in r5} == {"MÁQUINAS", "IMPLEMENTOS"}
    assert "Paradas operacionais de MÁQUINAS (6 h) maiores" in r5[0]["deducao"][0]
    api = Fake(com_ismael=True)
    api.prod[4]["unproductiveHours"] = "20.00"                                          # improdutiva > todas as paradas
    r5 = [x for x in achados(det(api)) if x["regra"] == "R5" and x["grupo"] == "MÁQUINAS"]
    assert "(26 h) maiores que as paradas de MÁQUINAS (14 h)" in r5[0]["deducao"][0]


def test_sem_cadastro_nao_corrige_sozinho():
    api = Fake(com_ismael=True); api.cadastro_fora = True
    d = det(api)
    assert d["cdos"][0]["avisos"] and d["resumo"]["cdos_sem_cadastro"] == 1
    xs = achados(d)
    assert [(x["regra"], x["tipo"]) for x in xs] == [("R2", "revisar")] and "corpo" not in xs[0]
    assert any("categoria desconhecida" in a for a in d["cdos"][0]["avisos"])
    assert cc.aplicar(api, d, [xs[0]["id"]], log=lambda m: None)["aplicados"] == 0 and api.puts == []


def test_operacao_resolvida_pela_formacao_de_preco():
    x = achados(det(Fake(com_ismael=True, com_op_id=False)))[0]
    assert x["tipo"] == "corrigir" and x["corpo"] == PAYLOAD_REAL


def test_put_que_falha_nao_e_repetido():
    api = Fake(com_ismael=True); d = det(api); api.falhar_put = True
    r = cc.aplicar(api, d, [achados(d)[0]["id"]], log=lambda m: None)
    assert r["itens"][0]["situacao"] == "conferir" and api.puts == []


def test_falta_apontar_e_grupo_sem_mao_de_obra():
    api = Fake(com_ismael=True)
    api.prod = [p for p in api.prod if p["id"] != "p3"]            # TF presente 9 h, nada apontado
    api.mdo = [w for w in api.mdo if w["employee"]["name"] != "JOAO"]   # motorista apontado sem estar na MDO
    xs = {x["grupo"]: x for x in achados(det(api)) if x["regra"] == "R1"}
    assert xs["TRABALHADORES FLORESTAIS"]["diferenca"] == -9.0 and "Faltam 9 h" in xs["TRABALHADORES FLORESTAIS"]["deducao"][0]
    assert xs["MOTORISTAS"]["horas_presentes"] == 0 and "Nenhum colaborador" in xs["MOTORISTAS"]["deducao"][0]


def test_utilitarios():
    assert cc.num("1.234,50") == 1234.5 and cc.num("8.00") == 8.0 and cc.num(None) == 0
    assert cc.eh_veiculo("Caminhão Pipa") and cc.eh_veiculo("Ônibus") and not cc.eh_veiculo("Veículo Leve")
    assert not cc.eh_veiculo("Trator de Pneu") and not cc.eh_veiculo("Escavadeira")
    c = lambda n, t=None: cc.categoria_equip({"name": n, "type": {"name": t}})
    assert c("Trator de Pneu Leve", "Máquinas") == "MAQUINAS" and c("Subsolador", "Implementos") == "IMPLEMENTOS"
    assert c("Caminhão Pipa", "Veículos") == "VEICULOS" and c("Veículo Leve", "Veículos") == "VL"
    assert c("Ônibus") == "VEICULOS" and c("Trator de Pneu Leve") == "MAQUINAS"
    assert cc.grupo_funcao("Operador de Máquinas Pleno") == "OPERADORES" and cc.grupo_funcao("Encarregado Operacional") is None


def test_maquina_emprestada_de_outra_turma_e_classificada_pelo_patrimonio():
    api = Fake(com_ismael=True)
    api.maq.append(maq("EXTRA1", "Trator de Esteira", "0.00", [("Mecânicas", "4.00")]))   # fora do cadastro da turma
    d = det(api)
    assert [x["regra"] for x in achados(d)] == ["R2"] and not d["cdos"][0]["avisos"]
