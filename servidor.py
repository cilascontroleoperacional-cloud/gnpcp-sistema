import os
import json
import threading
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# --- Estado global da extração ---
estado = {
    "rodando": False,
    "progresso": [],
    "resultado": None,
    "erro": None,
    "iniciado_em": None,
    "finalizado_em": None,
}

# =========================================================
# API ProdControl (REST direto — substitui Playwright)
# =========================================================
API_BASE   = "https://prodcontrol.app.br"
PC_CPF     = os.environ.get("PRODCONTROL_CPF", "")        # DEVE ter pontuação (ex.: 000.000.000-00)
PC_SENHA   = os.environ.get("PRODCONTROL_PASSWORD", "")   # NUNCA versionar — só via env do Railway
PC_EMPRESA = os.environ.get("PRODCONTROL_COMPANY", "GL-HOLDING")   # com hífen (não é segredo)

# --- Google OAuth2 (mesmo método do serviço antigo no Render) ---
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")

# --- Contratos (contractId filtra server-side em /odc) ---
CONTRATOS = [
    {"nome": "ARAUCO",       "contractId": "20f59d50-b39a-4140-9aa7-6efcef3b05c5"},
    {"nome": "MS Florestal", "contractId": "bbff595d-2b32-4f35-8c43-20f9e944a46e"},
    {"nome": "Innovatech",   "contractId": "f11ab962-3a16-42ed-88e9-7604d6ccde19"},
    {"nome": "COLPAR",       "contractId": "49383261-b78c-4603-94d2-fb48064346f1"},
    {"nome": "LACAN",        "contractId": "5a5763bf-e84c-4027-831e-9f2c5e4a4f76"},
    {"nome": "Eucatex",      "contractId": "390ec113-d920-4f77-a260-eef7537cd7b7"},
]

# --- Colunas de saída (ordem exata do COMPILADO) ---
COLUNAS = [
    "CONTRATO", "Cód. Boletim", "Data do Boletim", "Competência", "CR", "Contrato",
    "Cód. Máquina", "Tipo", "Escala de Horas", "Mat. Supervisor", "Supervisor",
    "Mat. Encarregado", "Encarregado", "Turma", "Cód. Operação", "Operação",
    "Cód. Projeto", "Projeto", "Talhão", "Mat. Operador", "Operador",
    "Horas Trabalhadas", "Horas Paradas", "Produção", "Horímetro Inicial",
    "Horímetro Final", "Criado Por", "Atualizado Por", "Criado Em",
]

DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "1vdiXZ26okg2yxbotIZ437UwQkOoJv56d")


# =========================================================
# Logging
# =========================================================
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    linha = f"[{ts}] {msg}"
    estado["progresso"].append(linha)
    print(linha, flush=True)


# =========================================================
# Cliente da API ProdControl
# =========================================================
class ProdControlAPI:
    def __init__(self):
        self.token = None
        self.s = requests.Session()
        self._cache_tipo = {}   # asset_id -> resourceType.name

    def login(self):
        if not PC_CPF or not PC_SENHA:
            raise RuntimeError(
                "Credenciais ausentes: defina PRODCONTROL_CPF e PRODCONTROL_PASSWORD "
                "nas variáveis de ambiente do Railway."
            )
        r = self.s.post(f"{API_BASE}/login", json={
            "cpf": PC_CPF, "password": PC_SENHA, "company": PC_EMPRESA
        }, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Login falhou ({r.status_code}): {r.text[:200]}")
        self.token = r.json()["token"]
        log("Login na API ProdControl OK (token 8h).")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path):
        url = f"{API_BASE}{path}"
        r = self.s.get(url, headers=self._headers(), timeout=60)
        if r.status_code == 401:           # token expirou -> re-login 1x
            log("Token expirado, refazendo login...")
            self.login()
            r = self.s.get(url, headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json()

    def tipo_maquina(self, asset_id):
        """Resolve o Tipo (resourceType.name) do patrimônio, com cache."""
        if not asset_id:
            return ""
        if asset_id in self._cache_tipo:
            return self._cache_tipo[asset_id]
        try:
            a = self.get(f"/assets/{asset_id}")
            nome = (a.get("resourceType") or {}).get("name", "") or ""
        except Exception:
            nome = ""
        self._cache_tipo[asset_id] = nome
        return nome

    def coletar_ids(self, datas_alvo):
        """
        Varre /odc por contrato (newest-first), coletando ids cujo
        bulletinDate está em datas_alvo (set de 'YYYY-MM-DD').
        Para a paginação quando a página inteira é mais antiga que a menor data.
        Retorna [(odc_id, nome_contrato), ...]
        """
        min_data = min(datas_alvo)
        ids = []
        for c in CONTRATOS:
            nome, cid = c["nome"], c["contractId"]
            page, total_pages, achados = 1, 1, 0
            while page <= total_pages:
                data = self.get(f"/odc?contractId={cid}&limit=255&page={page}")
                items = data.get("items", [])
                total_pages = data.get("meta", {}).get("totalPages", 1)
                if not items:
                    break
                for it in items:
                    bd = it.get("bulletinDate", "")
                    if bd in datas_alvo:
                        ids.append((it["id"], nome))
                        achados += 1
                page_min = min((it.get("bulletinDate", "9999-99-99") for it in items), default="0000")
                if page_min < min_data:        # resto das páginas é mais antigo
                    break
                page += 1
            log(f"  {nome}: {achados} boletins na janela")
        return ids

    def montar_linhas(self, ids):
        """Para cada odc_id baixa o detalhe e gera 1 linha por máquina."""
        linhas = []
        for odc_id, nome_contrato in ids:
            d = self.get(f"/odc/{odc_id}")
            h_cls   = d.get("class") or {}
            cc      = (h_cls.get("costCenter") or {})
            superv  = d.get("supervisor") or {}
            leader  = d.get("leader") or {}
            comp    = ((d.get("competenceCalendar") or {}).get("competence") or {})
            contrato= d.get("contract") or {}
            data_bol= _fmt_data(d.get("bulletinDate", ""))
            h_criado = (d.get("createdBy") or {}).get("name", "")
            h_atualiz= (d.get("updatedBy") or {}).get("name", "")
            h_criadoem = d.get("createdAt", "")

            for m in d.get("operationDailyControlMachines", []):
                asset  = m.get("asset") or {}
                emp    = m.get("employee") or {}
                oper   = ((m.get("priceFormation") or {}).get("operation") or {})
                proj   = m.get("project") or {}
                plot   = m.get("plot") or {}
                paradas= sum(_num(s.get("time")) for s in (m.get("odcMachineStoppages") or []))

                linhas.append({
                    "CONTRATO":          nome_contrato,
                    "Cód. Boletim":      d.get("code", ""),
                    "Data do Boletim":   data_bol,
                    "Competência":       comp.get("name", ""),
                    "CR":                cc.get("name", ""),
                    "Contrato":          contrato.get("description", ""),
                    "Cód. Máquina":      asset.get("code", ""),
                    "Tipo":              self.tipo_maquina(asset.get("id")),
                    "Escala de Horas":   d.get("hourScale", ""),
                    "Mat. Supervisor":   superv.get("employeeNumber", ""),
                    "Supervisor":        superv.get("name", ""),
                    "Mat. Encarregado":  leader.get("employeeNumber", ""),
                    "Encarregado":       leader.get("name", ""),
                    "Turma":             h_cls.get("name", ""),
                    "Cód. Operação":     oper.get("code", ""),
                    "Operação":          oper.get("name", ""),
                    "Cód. Projeto":      proj.get("code", ""),
                    "Projeto":           proj.get("name", ""),
                    "Talhão":            plot.get("name", ""),
                    "Mat. Operador":     emp.get("employeeNumber", ""),
                    "Operador":          emp.get("name", ""),
                    "Horas Trabalhadas": m.get("workedHours", ""),
                    "Horas Paradas":     f"{paradas:.2f}" if paradas else "",
                    "Produção":          m.get("productiveAmount", ""),
                    "Horímetro Inicial": m.get("hourMeterStart", ""),
                    "Horímetro Final":   m.get("hourMeterEnd", ""),
                    "Criado Por":        (m.get("createdBy") or {}).get("name", "") or h_criado,
                    "Atualizado Por":    (m.get("updatedBy") or {}).get("name", "") or h_atualiz,
                    "Criado Em":         _fmt_dt(m.get("createdAt", "") or h_criadoem),
                })
        return linhas


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return 0.0

def _fmt_data(iso):
    """'2026-10-23' -> '23/10/2026'"""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso

def _fmt_dt(iso):
    """'2026-10-23T15:03:26.413Z' -> '23/10/2026 15:03'"""
    try:
        return datetime.strptime(iso[:16], "%Y-%m-%dT%H:%M").strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso


# =========================================================
# Extração principal (thread)
# =========================================================
def extrair_boletim(datas_alvo, label_arquivo):
    """datas_alvo: set de 'YYYY-MM-DD'. label_arquivo: sufixo do nome do .xlsx"""
    estado["rodando"] = True
    estado["progresso"] = []
    estado["resultado"] = None
    estado["erro"] = None
    estado["iniciado_em"] = datetime.now().isoformat()

    try:
        api = ProdControlAPI()
        api.login()

        log(f"Coletando boletins da janela: {sorted(datas_alvo)[0]} a {sorted(datas_alvo)[-1]}")
        ids = api.coletar_ids(datas_alvo)
        log(f"Total de boletins na janela: {len(ids)}")

        linhas = api.montar_linhas(ids)
        log(f"Linhas de máquina geradas: {len(linhas)}")

        nome_arquivo = f"COMPILADO_MAQUINARIO_{label_arquivo}.xlsx"
        caminho = f"/tmp/{nome_arquivo}"
        gerar_excel(linhas, label_arquivo, caminho)
        log(f"Excel gerado: {nome_arquivo}")

        link_drive = upload_drive(caminho, nome_arquivo)
        log(f"Arquivo salvo no Drive: {link_drive}")

        estado["resultado"] = {
            "arquivo": nome_arquivo,
            "total_registros": len(linhas),
            "link_drive": link_drive,
            "por_contrato": contar_por_contrato(linhas),
        }
    except Exception as e:
        log(f"ERRO FATAL: {e}")
        estado["erro"] = str(e)
    finally:
        estado["rodando"] = False
        estado["finalizado_em"] = datetime.now().isoformat()


def contar_por_contrato(dados):
    contagem = {}
    for row in dados:
        c = row.get("CONTRATO", "?")
        contagem[c] = contagem.get(c, 0) + 1
    return contagem


# =========================================================
# Excel (reaproveitado — formatação GN)
# =========================================================
def gerar_excel(dados, label, caminho):
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"BOLETIM_{label}"[:31]

    cabecalho_fill = PatternFill("solid", fgColor="1F3864")
    cabecalho_font = Font(color="FFFFFF", bold=True, size=10)
    zebra_fill     = PatternFill("solid", fgColor="DCE6F1")

    for col_idx, col_nome in enumerate(COLUNAS, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_nome)
        cell.fill = cabecalho_fill
        cell.font = cabecalho_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, row in enumerate(dados, 2):
        for col_idx, col_nome in enumerate(COLUNAS, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=row.get(col_nome, ""))
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
            cell.alignment = Alignment(vertical="center")

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"

    for col_idx in range(1, len(COLUNAS) + 1):
        max_w = 10
        col_letter = get_column_letter(col_idx)
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    max_w = max(max_w, len(str(cell.value)) + 2)
        ws.column_dimensions[col_letter].width = min(max_w, 40)

    ws2 = wb.create_sheet("RESUMO")
    for j, titulo in enumerate(["Contrato", "Registros"], 1):
        c = ws2.cell(1, j, titulo); c.fill = cabecalho_fill; c.font = cabecalho_font
    contagem = contar_por_contrato(dados)
    nomes = [c["nome"] for c in CONTRATOS]
    for i, nome in enumerate(nomes, 2):
        ws2.cell(i, 1, nome)
        ws2.cell(i, 2, contagem.get(nome, 0))
    ws2.cell(len(nomes) + 2, 1, "TOTAL").font = Font(bold=True)
    ws2.cell(len(nomes) + 2, 2, len(dados)).font = Font(bold=True)
    ws2.freeze_panes = "A2"

    wb.save(caminho)


# =========================================================
# Google Drive (reaproveitado)
# =========================================================
def get_access_token():
    """Troca o refresh token por um access token via Google OAuth2."""
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    r = requests.post(token_url, data=payload, timeout=30)
    if r.status_code == 200:
        return r.json().get("access_token")
    log(f"Erro ao renovar token Google ({r.status_code}): {r.text[:120]}")
    return None


def upload_drive(caminho_local, nome_arquivo):
    """Upload para o Google Drive usando OAuth2 (client_id/secret/refresh_token)."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN):
        log("Credenciais Google OAuth2 ausentes — pulando upload (arquivo fica só no servidor).")
        return None

    access_token = get_access_token()
    if not access_token:
        return None

    creds = Credentials(token=access_token)
    service = build("drive", "v3", credentials=creds)

    pasta_id = encontrar_ou_criar_pasta(service, "Boletins_2026", DRIVE_FOLDER_ID)
    file_metadata = {"name": nome_arquivo, "parents": [pasta_id]}
    media = MediaFileUpload(caminho_local,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    arquivo = service.files().create(body=file_metadata, media_body=media,
        fields="id,webViewLink").execute()
    return arquivo.get("webViewLink", "")


def encontrar_ou_criar_pasta(service, nome, parent_id):
    query = (f"name='{nome}' and mimeType='application/vnd.google-apps.folder' "
             f"and '{parent_id}' in parents and trashed=false")
    res = service.files().list(q=query, fields="files(id)").execute()
    arquivos = res.get("files", [])
    if arquivos:
        return arquivos[0]["id"]
    meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    return service.files().create(body=meta, fields="id").execute()["id"]


# =========================================================
# Endpoints Flask
# =========================================================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})


@app.route("/status", methods=["GET"])
def status():
    return jsonify(estado)


@app.route("/extrair-boletim", methods=["POST"])
def extrair():
    if estado["rodando"]:
        return jsonify({"erro": "Já existe uma extração em andamento. Aguarde."}), 409

    body = request.get_json(silent=True) or {}

    # Modo 1: data única "DD/MM/YYYY"
    if body.get("data"):
        data = body["data"]
        if not re.match(r"^\d{2}/\d{2}/\d{4}$", data):
            return jsonify({"erro": "Formato inválido. Use DD/MM/YYYY"}), 400
        iso = datetime.strptime(data, "%d/%m/%Y").strftime("%Y-%m-%d")
        datas = {iso}
        label = data.replace("/", "-")

    # Modo 2: últimos N dias  {"dias": 30}
    elif body.get("dias"):
        n = int(body["dias"])
        hoje = datetime.now()
        datas = {(hoje - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)}
        label = f"ULTIMOS_{n}D_{hoje.strftime('%d-%m-%Y')}"

    # Modo 3: intervalo {"inicio":"DD/MM/YYYY","fim":"DD/MM/YYYY"}
    elif body.get("inicio") and body.get("fim"):
        di = datetime.strptime(body["inicio"], "%d/%m/%Y")
        df = datetime.strptime(body["fim"], "%d/%m/%Y")
        dias = (df - di).days
        datas = {(di + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dias + 1)}
        label = f"{body['inicio'].replace('/','-')}_a_{body['fim'].replace('/','-')}"
    else:
        return jsonify({"erro": "Informe 'data', 'dias' ou 'inicio'+'fim'."}), 400

    t = threading.Thread(target=extrair_boletim, args=(datas, label), daemon=True)
    t.start()
    return jsonify({"mensagem": f"Extração iniciada ({label}). Consulte /status."})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
