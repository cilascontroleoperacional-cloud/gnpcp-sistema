"""Rotas /cdo/* do servidor.py com a API do ProdControl simulada."""
import os, sys, time
os.environ["API_KEY"] = "chave-teste"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import servidor
from test_correcao_cdo import Fake, PAYLOAD_REAL

H = {"X-API-Key": "chave-teste"}


def esperar(c):
    for _ in range(100):
        s = c.get("/cdo/status", headers=H).get_json()
        if not s["rodando"]:
            return s
        time.sleep(0.05)
    raise AssertionError("não terminou")


def test_fluxo_completo(monkeypatch):
    api = Fake(cleiton_presente=True); api.login = lambda: None
    monkeypatch.setattr(servidor, "ProdControlAPI", lambda: api)
    logs = []
    monkeypatch.setattr(servidor, "_registrar_log_base", lambda *a: logs.append(a))
    notas = []
    monkeypatch.setattr(servidor, "_registrar_ranking", lambda det: notas.append(det["todos"]) or {"gravadas": 1})
    servidor.estado_cdo.update(deteccao=None, aplicacao=None, rodando=False)
    c = servidor.app.test_client()

    assert c.post("/cdo/detectar", json={}).status_code == 401                       # sem chave
    assert c.get("/cdo/status").status_code == 401
    assert c.post("/cdo/aplicar", json={"ids": ["x"]}, headers=H).status_code == 409  # sem detecção
    assert c.post("/cdo/detectar", json={"data": "12-11-2026"}, headers=H).status_code == 400
    assert c.post("/cdo/detectar", json={"inicio": "01/10/2026", "fim": "12/11/2026"}, headers=H).status_code == 400
    assert c.post("/cdo/detectar", json={"data": "12/11/2026", "contratos": ["xx"]}, headers=H).status_code == 400

    assert c.post("/cdo/detectar", json={"data": "12/11/2026", "contratos": ["lacan"]}, headers=H).status_code == 200
    s = esperar(c)
    assert s["erro"] is None and s["deteccao"]["resumo"]["corrigir"] == 1
    assert s["deteccao"]["resumo"]["ranking"] == {"gravadas": 1} and "todos" not in s["deteccao"]
    assert len(notas) == 1 and notas[0][0]["regras"] == ["R2"]
    assert len(notas) == 1
    ach = s["deteccao"]["cdos"][0]["achados"][0]
    assert s["deteccao"]["cdos"][0]["cdo"] == 53489 and ach["corpo"] == PAYLOAD_REAL

    assert c.post("/cdo/aplicar", json={"ids": []}, headers=H).status_code == 400
    assert c.post("/cdo/aplicar", json={"ids": [ach["id"]]}, headers=H).status_code == 200
    s = esperar(c)
    assert s["aplicacao"]["aplicados"] == 1 and len(api.puts) == 1 and len(logs) == 1
    assert api.puts[0][0] == "/odc/production/" + PAYLOAD_REAL["id"]
    c.post("/cdo/detectar", json={"data": "12/11/2026", "contratos": ["LACAN"], "ranking": False}, headers=H)
    s2 = esperar(c)                                                # ranking desligado: não chama a planilha
    assert "ranking" not in s2["deteccao"]["resumo"] and s2["deteccao"]["cdos"] == [] and len(notas) == 1


def test_data_padrao_e_ontem():
    ini, fim = servidor._periodo_cdo({})
    assert ini == fim == (servidor.agora_ms() - servidor.timedelta(days=1)).strftime("%Y-%m-%d")
