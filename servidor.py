import os
import json
import threading
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = Flask(__name__, static_folder='interface', static_url_path='')
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

# --- Credenciais ProdControl ---
PC_URL    = "https://prodcontrol.prodsistem.com.br"
PC_CPF    = os.environ.get("PRODCONTROL_EMAIL", "030.456.481-85")
PC_SENHA  = os.environ.get("PRODCONTROL_SENHA", "030456")
PC_EMPRESA = "GL Holding"

# --- Google OAuth2 ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "https://gn-pcp-sistema.onrender.com/oauth-callback")

# --- Contratos ---
CONTRATOS = [
    {"nome": "ARAUCO",       "supplierId": "a645df98-9354-41c5-bcb2-38c06140a6f2", "contractId": "20f59d50-b39a-4140-9aa7-6efcef3b05c5"},
    {"nome": "MS Florestal", "supplierId": "b2dec87c-5c7d-49d8-86a5-e153887ea6f0", "contractId": "bbff595d-2b32-4f35-8c43-20f9e944a46e"},
    {"nome": "Innovatech",   "supplierId": "c1cb43c9-30e4-43db-9520-abc634af4c90", "contractId": "f11ab962-3a16-42ed-88e9-7604d6ccde19"},
    {"nome": "COLPAR",       "supplierId": "c1cb43c9-30e4-43db-9520-abc634af4c90", "contractId": "49383261-b78c-4603-94d2-fb48064346f1"},
    {"nome": "LACAN",        "supplierId": "23773a15-868b-4206-b816-2da24db43ac4", "contractId": "5a5763bf-e84c-4027-831e-9f2c5e4a4f76"},
    {"nome": "Eucatex",      "supplierId": "894a9862-633e-4221-acc6-1177893f1bb9", "contractId": "390ec113-d920-4f77-a260-eef7537cd7b7"},
]

COLUNAS = [
    "CONTRATO", "Cód. Boletim", "Data do Boletim", "Competência", "CR", "Contrato",
    "Cód. Máquina", "Tipo", "Escala de Horas", "Mat. Supervisor", "Supervisor",
    "Mat. Encarregado", "Encarregado", "Turma", "Cód. Operação", "Operação",
    "Cód. Projeto", "Projeto", "Talhão", "Mat. Operador", "Operador",
    "Horas Trabalhadas", "Horas Paradas", "Produção", "Horímetro Inicial",
    "Horímetro Final", "Criado Por", "Atualizado Por", "Criado Em",
]

DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "1vdiXZ26okg2yxbotIZ437UwQkOoJv56d")

# JS injetado
JS_SET_FORM = r"""
window.__setFormAndSearch = async function(supplierId, contractId, startDate, endDate) {
  function findController(fieldName) {
    const input = document.querySelector(`input[name="${fieldName}"]`);
    if (!input) return null;
    const sfk = Object.keys(input).find(k => k.startsWith('__reactFiber'));
    let fiber = input[sfk];
    for (let i = 0; i < 20 && fiber; i++) {
      fiber = fiber.return;
      const props = fiber?.memoizedProps;
      if (props?.name === fieldName && typeof props?.onChange === 'function') return props.onChange;
    }
    return null;
  }
  const setSupplier = findController('supplierId');
  const setContract = findController('contractId');
  if (!setSupplier || !setContract) return {erro: 'controllers nao encontrados'};
  setSupplier(supplierId);
  await new Promise(r => setTimeout(r, 400));
  setContract(contractId);
  await new Promise(r => setTimeout(r, 400));
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  const si = document.getElementById('startDate');
  const ei = document.getElementById('endDate');
  if (!si || !ei) return {erro: 'campos de data nao encontrados'};
  setter.call(si, startDate); si.dispatchEvent(new Event('input',{bubbles:true})); si.dispatchEvent(new Event('change',{bubbles:true}));
  setter.call(ei, endDate);   ei.dispatchEvent(new Event('input',{bubbles:true})); ei.dispatchEvent(new Event('change',{bubbles:true}));
  await new Promise(r => setTimeout(r, 300));
  const buscar = [...document.querySelectorAll('button')].find(b => b.textContent.trim().toUpperCase().includes('BUSCAR'));
  if (!buscar) return {erro: 'botao BUSCAR nao encontrado'};
  buscar.click();
  await new Promise(r => setTimeout(r, 6000));
  const rows = document.querySelectorAll('table tbody tr');
  return {rows: rows.length};
};
"""

JS_EXTRACT_PAGES = r"""
window.__extractAllPages = async function(contratoLabel) {
  const allRows = [];
  const pageButtons = [...document.querySelectorAll('button')].filter(b => /^\d+$/.test(b.textContent.trim()));
  const totalPages = pageButtons.length > 0 ? Math.max(...pageButtons.map(b => parseInt(b.textContent.trim()))) : 1;
  for (let p = 1; p <= totalPages; p++) {
    if (p > 1) {
      const pageBtn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === String(p));
      if (pageBtn) { pageBtn.click(); await new Promise(r => setTimeout(r, 2000)); }
    }
    const headers = [...document.querySelectorAll('table thead th')].map(th => th.textContent.trim());
    const rows = [...document.querySelectorAll('table tbody tr')];
    for (const row of rows) {
      const cells = [...row.querySelectorAll('td')].map(td => td.textContent.trim());
      if (cells.length > 0 && cells.some(c => c)) {
        const rowObj = {CONTRATO: contratoLabel};
        headers.forEach((h, i) => rowObj[h] = cells[i] || '');
        allRows.push(rowObj);
      }
    }
  }
  return allRows;
};
"""

def get_access_token():
    """Troca refresh token por access token via Google"""
    import requests
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    r = requests.post(token_url, data=payload)
    if r.status_code == 200:
        return r.json()["access_token"]
    return None

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    linha = f"[{ts}] {msg}"
    estado["progresso"].append(linha)
    print(linha, flush=True)

def extrair_boletim(data_str: str):
    """data_str no formato DD/MM/YYYY"""
    from playwright.sync_api import sync_playwright
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter

    estado["rodando"] = True
    estado["progresso"] = []
    estado["resultado"] = None
    estado["erro"] = None
    estado["iniciado_em"] = datetime.now().isoformat()

    todos_dados = []

    try:
        log(f"Iniciando extração para data: {data_str}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page()

            # --- Login ---
            log("Acessando ProdControl...")
            page.goto(PC_URL, wait_until="networkidle", timeout=30000)
            page.evaluate("""
                document.getElementById('company').value = '';
                document.getElementById('email').value = '';
                document.getElementById('password').value = '';
            """)
            page.fill("#company", PC_EMPRESA)
            page.fill("#email", PC_CPF)
            page.fill("#password", PC_SENHA)
            page.evaluate("document.querySelector('form').submit()")
            page.wait_for_load_state("networkidle", timeout=20000)
            log("Login realizado.")

            # --- Navegar para Boletim de Maquinário ---
            page.goto(f"{PC_URL}/boletim-maquinario", wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(2000)

            # Injetar funções JS
            page.evaluate(JS_SET_FORM)
            page.evaluate(JS_EXTRACT_PAGES)

            # --- Iterar contratos ---
            for contrato in CONTRATOS:
                nome = contrato["nome"]
                log(f"Extraindo {nome}...")

                try:
                    result = page.evaluate(
                        f"window.__setFormAndSearch('{contrato['supplierId']}', '{contrato['contractId']}', '{data_str}', '{data_str}')"
                    )

                    if isinstance(result, dict) and "erro" in result:
                        log(f"  {nome}: ERRO — {result['erro']}")
                        continue

                    n_rows = result.get("rows", 0) if isinstance(result, dict) else 0
                    log(f"  {nome}: {n_rows} linhas encontradas")

                    if n_rows == 0:
                        log(f"  {nome}: sem apontamento — pulando extração")
                        continue

                    # Reinjeta funções
                    page.evaluate(JS_SET_FORM)
                    page.evaluate(JS_EXTRACT_PAGES)

                    dados = page.evaluate(f"window.__extractAllPages('{nome}')")
                    todos_dados.extend(dados)
                    log(f"  {nome}: {len(dados)} registros extraídos")

                except Exception as e:
                    log(f"  {nome}: FALHA — {e}")

            browser.close()

        log(f"Extração concluída. Total: {len(todos_dados)} registros")

        # --- Gerar Excel ---
        nome_arquivo = f"COMPILADO_MAQUINARIO_{data_str.replace('/', '-')}.xlsx"
        caminho = f"/tmp/{nome_arquivo}"
        gerar_excel(todos_dados, data_str, caminho)
        log(f"Excel gerado: {nome_arquivo}")

        # --- Upload Google Drive ---
        link_drive = upload_drive(caminho, nome_arquivo)
        log(f"Arquivo salvo no Drive: {link_drive}")

        estado["resultado"] = {
            "arquivo": nome_arquivo,
            "total_registros": len(todos_dados),
            "link_drive": link_drive,
            "por_contrato": contar_por_contrato(todos_dados),
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

def gerar_excel(dados, data_str, caminho):
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    data_aba = data_str.replace("/", "-")
    ws.title = f"BOLETIM_{data_aba}"

    cabecalho_fill = PatternFill("solid", fgColor="1F3864")
    cabecalho_font = Font(color="FFFFFF", bold=True, size=10)
    zebra_fill     = PatternFill("solid", fgColor="DCE6F1")

    colunas_presentes = COLUNAS[:]
    for col_idx, col_nome in enumerate(colunas_presentes, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_nome)
        cell.fill = cabecalho_fill
        cell.font = cabecalho_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, row in enumerate(dados, 2):
        for col_idx, col_nome in enumerate(colunas_presentes, 1):
            valor = row.get(col_nome, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=valor)
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
            cell.alignment = Alignment(vertical="center")

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"

    for col_idx in range(1, len(colunas_presentes) + 1):
        max_w = 10
        col_letter = get_column_letter(col_idx)
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    max_w = max(max_w, len(str(cell.value)) + 2)
        ws.column_dimensions[col_letter].width = min(max_w, 40)

    ws2 = wb.create_sheet("RESUMO")
    ws2.cell(1, 1, "Contrato").fill = cabecalho_fill
    ws2.cell(1, 1).font = cabecalho_font
    ws2.cell(1, 2, "Registros").fill = cabecalho_fill
    ws2.cell(1, 2).font = cabecalho_font

    contagem = contar_por_contrato(dados)
    nomes_contratos = [c["nome"] for c in CONTRATOS]
    for i, nome in enumerate(nomes_contratos, 2):
        ws2.cell(i, 1, nome)
        ws2.cell(i, 2, contagem.get(nome, 0))

    ws2.cell(len(nomes_contratos) + 2, 1, "TOTAL").font = Font(bold=True)
    ws2.cell(len(nomes_contratos) + 2, 2, len(dados)).font = Font(bold=True)
    ws2.freeze_panes = "A2"

    wb.save(caminho)

def upload_drive(caminho_local, nome_arquivo):
    """Upload para Google Drive usando OAuth2"""
    try:
        access_token = get_access_token()
        if not access_token:
            log("Erro ao obter access token")
            return None

        creds = Credentials(token=access_token)
        service = build("drive", "v3", credentials=creds)

        pasta_id = encontrar_ou_criar_pasta(service, "Boletins_2026", DRIVE_FOLDER_ID)

        file_metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaFileUpload(caminho_local, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        arquivo = service.files().create(body=file_metadata, media_body=media, fields="id,webViewLink").execute()
        return arquivo.get("webViewLink", "")
    except Exception as e:
        log(f"Erro no upload: {e}")
        return None

def encontrar_ou_criar_pasta(service, nome, parent_id):
    query = f"name='{nome}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
    res = service.files().list(q=query, fields="files(id)").execute()
    arquivos = res.get("files", [])
    if arquivos:
        return arquivos[0]["id"]
    meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    pasta = service.files().create(body=meta, fields="id").execute()
    return pasta["id"]

@app.route("/", methods=["GET"])
def index():
    return send_from_directory('interface', 'index.html')

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "rodando": estado["rodando"],
        "progresso": estado["progresso"],
        "resultado": estado["resultado"],
        "erro": estado["erro"],
        "iniciado_em": estado["iniciado_em"],
        "finalizado_em": estado["finalizado_em"],
    })

@app.route("/extrair-boletim", methods=["POST"])
def extrair():
    if estado["rodando"]:
        return jsonify({"erro": "Já existe uma extração em andamento. Aguarde."}), 409

    body = request.get_json(silent=True) or {}
    data = body.get("data", "")

    if not re.match(r"^\d{2}/\d{2}/\d{4}$", data):
        return jsonify({"erro": "Formato de data inválido. Use DD/MM/YYYY"}), 400

    t = threading.Thread(target=extrair_boletim, args=(data,), daemon=True)
    t.start()

    return jsonify({"mensagem": f"Extração iniciada para {data}. Consulte /status para acompanhar."})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
