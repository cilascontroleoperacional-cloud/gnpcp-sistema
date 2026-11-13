"""Ranking de apontamentos: montagem das linhas e gravação na planilha (Google simulado)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import correcao_cdo as cc
import ranking_cdo as rk
from test_correcao_cdo import Fake, LACAN, corrigido

D12 = rk.serial("2026-11-12")


class Planilha:
    """Imita atualizar_base.Base: valores(), meta(), batch(), _req()."""
    def __init__(self, linhas=None, grade=1000):
        self.linhas = linhas if linhas is not None else [
            [46255, 1410, "JOSE VITOR MORAES SANTOS", "RENILDO DA CONCEIÇÃO OLIVEIRA", "SIM"],
            [46315, 1270, "ADRIANO BARROS DA COSTA", "JOÃO VITOR TONETO", "SIM"],
            [46315, 1270, "ADRIANO BARROS DA COSTA", "RENILDO DA CONCEIÇÃO OLIVEIRA", "SIM"]]
        self.grade, self.chamadas = grade, []

    def valores(self, rngs):
        assert rngs == ["BASE_APONTAMENTOS!A4:D5000"]
        return [[r[:4] for r in self.linhas] + [["", "", "", ""]]]      # linha em branco no fim é ignorada

    def meta(self):
        return {"sheets": [{"properties": {"sheetId": 7, "title": "BASE_APONTAMENTOS", "gridProperties": {"rowCount": self.grade}}}]}

    def batch(self, reqs):
        self.chamadas.append(("batch", reqs))

    def _req(self, metodo, path, **kw):
        self.chamadas.append((metodo, path, kw))
        self.linhas += kw["json"]["values"]


def todos(api):
    return cc.detectar(api, LACAN, "2026-11-12", "2026-11-12", log=lambda m: None)["todos"]


def test_data_local_e_serial():
    assert rk.data_local("2026-11-13T01:49:56.973Z") == "2026-11-12"       # 21:49 em MS, ainda dia 12
    assert rk.data_local("2026-11-13T04:00:00.000Z") == "2026-11-13" and rk.data_local(None) == ""
    assert rk.serial("2026-08-21") == 46255                                # igual à 1ª linha da planilha


def test_nota_do_cdo_como_o_encarregado_deixou():
    linhas, sem = rk.montar(todos(Fake()))
    assert sem == [] and len(linhas) == 1
    x = linhas[0]
    assert (x["data"], x["cr"], x["supervisor"]) == ("2026-11-12", 1270, "ADRIANO BARROS DA COSTA")
    assert x["respostas"] == {"E": "SIM", "F": "SIM", "G": "NÃO", "H": "SIM", "I": "SIM", "J": "SIM", "K": "SIM"}
    assert x["obs"] == "CDO 53489: horas por função fora de 100%; motorista sem veículo com hora trabalhada"


def test_nota_limpa_e_nota_com_todos_os_erros():
    assert rk.montar(todos(corrigido()))[0][0]["respostas"] == dict.fromkeys("EFGHIJK", "SIM")
    api = Fake(gntp282_errada=True)
    api.cab["createdAt"] = "2026-11-13T15:00:00.000Z"                      # criado no dia seguinte
    api.cab["createdBy"] = {"name": "Luiz Gustavo Cardoso"}                # cadastrado por outra pessoa
    api.prod[4]["productiveAmount"] = "0.00"
    api.mdo = [w for w in api.mdo if w["employee"]["name"] != "ROSIVALDO"]
    api.maq = [m for m in api.maq if m["asset"]["code"] != "GH37"]
    x = rk.montar(todos(api))[0][0]
    assert x["respostas"] == dict.fromkeys("EFGHIJK", "NÃO")
    assert x["obs"].startswith("CDO 53489: CDO cadastrado por outra pessoa; CDO criado fora do dia; ")


def test_turma_de_apoio_e_cdo_sem_cadastro_ficam_fora():
    t = todos(Fake())
    assert rk.montar([dict(t[0], turma="Apoio e Manutenção GN1270")]) == ([], [])
    linhas, sem = rk.montar([dict(t[0], cadastro_ok=False)])
    assert linhas == [] and "CDO 53489" in sem[0]
    assert rk.montar([dict(t[0], cr="", contrato="COLPAR")])[0][0]["cr"] == 1421


def test_dois_cdos_do_mesmo_encarregado_no_dia_viram_uma_linha():
    t = todos(Fake())[0]
    linhas, _ = rk.montar([dict(t, regras=["R6"]), dict(t, cdo=53490, regras=["R3"], criado_por="Outra Pessoa")])
    assert len(linhas) == 1 and linhas[0]["regras"] == ["R3", "R6"] and linhas[0]["cdos"] == ["53489", "53490"]
    assert linhas[0]["respostas"]["F"] == "NÃO" and linhas[0]["respostas"]["I"] == "NÃO" and linhas[0]["respostas"]["K"] == "NÃO"


def test_grava_no_fim_com_a_grafia_da_planilha_e_nao_duplica():
    p = Planilha()
    det = {"todos": todos(Fake())}
    r = rk.registrar(p, det, log=lambda m: None)
    assert r == {"gravadas": 1, "ja_existiam": 0, "linha_inicial": 7, "linha_final": 7, "sem_nota": [],
                 "com_erro": 1, "avaliados": 1}
    metodo, path, kw = p.chamadas[0]
    assert metodo == "PUT" and path == "/values/BASE_APONTAMENTOS%21A7%3AN7" and kw["params"] == {"valueInputOption": "USER_ENTERED"}
    assert kw["json"]["values"] == [[D12, 1270, "ADRIANO BARROS DA COSTA", "RENILDO DA CONCEIÇÃO OLIVEIRA",
                                     "SIM", "SIM", "NÃO", "SIM", "SIM", "SIM", "SIM",
                                     '=IF(D7="";0;COUNTIF(E7:K7;"NÃO"))', '=IF(D7="";0;COUNTIF(E7:K7;"NÃO")*10)',
                                     "CDO 53489: horas por função fora de 100%; motorista sem veículo com hora trabalhada"]]
    fmt = p.chamadas[1][1][0]["repeatCell"]
    assert fmt["range"] == {"sheetId": 7, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 0, "endColumnIndex": 1}
    # segunda conferência do mesmo dia (já corrigido) NÃO troca a nota original
    r2 = rk.registrar(p, {"todos": todos(corrigido())}, log=lambda m: None)
    assert r2["gravadas"] == 0 and r2["ja_existiam"] == 1 and len(p.chamadas) == 2 and len(p.linhas) == 4


def test_planilha_cheia_ganha_linhas_e_nome_novo_vai_em_maiusculas():
    p = Planilha(grade=6)
    r = rk.gravar(p, rk.montar([dict(todos(Fake())[0], encarregado="Fulano de Tal", supervisor="Beltrano")])[0], log=lambda m: None)
    assert r["gravadas"] == 1 and p.chamadas[0][1][0]["appendDimension"]["length"] == 51
    assert p.linhas[-1][2:4] == ["BELTRANO", "FULANO DE TAL"]
    assert rk.casar("JOAO VITOR TONETO SILVA", {"joao vitor toneto": "JOÃO VITOR TONETO"}) == "JOÃO VITOR TONETO"
    assert rk.gravar(Planilha(linhas=[]), [], log=lambda m: None) == {"gravadas": 0, "ja_existiam": 0}
