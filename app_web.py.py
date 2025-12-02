import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
import requests
import streamlit.components.v1 as components

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# SEU CANAL SECRETO DO NTFY
TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"

# --- INTERVALOS DE NOTIFICAÇÃO (EM MINUTOS) ---
INTERVALO_GERAL = 60 # O Robô vai checar e mandar o resumo a cada 60 minutos

# --- AUTO-REFRESH (60 segundos) ---
refresh_code = """
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 60000);
</script>
"""
components.html(refresh_code, height=0)

# Função para carregar imagem
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f: data = f.read()
        return base64.b64encode(data).decode()
    except: return ""

img_loading = get_img_as_base64("loading.gif")

# CSS (Dark Mode)
st.markdown(f"""
<style>
    .stApp {{ background-color: #0e1117; color: #e0e0e0; }}
    div[data-testid="metric-container"] {{
        background-color: #1f2937; border: 1px solid #374151;
        padding: 15px; border-radius: 10px;
    }}
    .stButton>button {{
        border-radius: 8px; font-weight: bold; text-transform: uppercase;
        background-image: linear-gradient(to right, #2563eb, #1d4ed8);
        border: none; color: white;
    }}
</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO E FUNÇÕES ---

def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

def enviar_resumo_push(lista_problemas):
    """
    Envia UMA única notificação com a lista de problemas
    Isso evita a cascata de mensagens.
    """
    qtd = len(lista_problemas)
    if qtd == 0: return False

    # Define urgência baseado no pior caso
    tem_atrasado = any("ATRASADO" in p['status'] for p in lista_problemas)
    
    if tem_atrasado:
        titulo = f"⛔ URGENTE: {qtd} Pendências Graves"
        tags = "rotating_light,skull"
        prio = "urgent" # Toca alto
    else:
        titulo = f"⚠️ ALERTA: {qtd} Prazos Próximos"
        tags = "warning"
        prio = "high"

    # Monta o texto do resumo (Máximo 5 linhas para não cortar)
    mensagem = "Resumo da Situação:\n"
    for p in lista_problemas[:5]:
        mensagem += f"- {p['doc']} ({p['status']})\n"
    
    if qtd > 5:
        mensagem += f"...e mais {qtd-5} itens."

    try:
        requests.post(
            f"https://ntfy.sh/{TOPICO_NOTIFICACAO}",
            data=mensagem.encode('utf-8'),
            headers={"Title": titulo.encode('utf-8'), "Priority": prio, "Tags": tags}
        )
        return True
    except:
        return False

def sincronizar_prazos_completo(df_novo):
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        ws.clear()
        df_salvar = df_novo.copy()
        df_salvar['Concluido'] = df_salvar['Concluido'].astype(str)
        # Garante data como string
        df_salvar['Vencimento'] = df_salvar['Vencimento'].astype(str).replace("NaT", "")
        
        lista_dados = [df_salvar.columns.values.tolist()] + df_salvar.values.tolist()
        ws.update(lista_dados)
        st.toast("✅ Salvo na nuvem!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def salvar_vistoria_db(lista_itens):
    try:
        sh = conectar_gsheets()
        try: ws = sh.worksheet("Vistorias")
        except: ws = sh.add_worksheet(title="Vistorias", rows=1000, cols=10)
        hoje = date.today().strftime("%d/%m/%Y")
        for item in lista_itens:
            ws.append_row([item['Setor'], item['Item'], item['Situação'], item['Gravidade'], item['Obs'], hoje])
    except: st.error("Erro ao salvar vistoria.")

def carregar_dados_prazos():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        dados = ws.get_all_records()
        df = pd.DataFrame(dados)
        if "Concluido" not in df.columns: df["Concluido"] = "False"
        
        # --- CORREÇÃO DA DATA (O SEGREDO) ---
        # Forçamos o pandas a entender que o primeiro número é DIA (%d/%m/%Y)
        # errors='coerce' transforma erros em NaT (que tratamos depois)
        df['Vencimento'] = pd.to_datetime(df['Vencimento'], format="%d/%m/%Y", errors='coerce').dt.date
        
        df['Concluido'] = df['Concluido'].astype(str).str.upper() == 'TRUE'
        return df
    except Exception as e:
        # st.error(f"Erro ao ler datas: {e}") # Debug se precisar
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status", "Concluido"])

def calcular_status(data_venc, concluido):
    if concluido: return 999, "✅ RESOLVIDO"
    if pd.isnull(data_venc): return 0, "⚪ DATA INVÁLIDA"
    
    hoje = date.today()
    dias = (data_venc - hoje).days
    
    # NOVAS REGRAS
    if dias < 0: return dias, "⛔ ATRASADO"
    elif dias == 0: return dias, "💥 VENCE HOJE"
    elif dias <= 7: return dias, "🔴 CRÍTICO" # Até 7 dias
    elif dias <= 10: return dias, "🟠 ALTO"   # Até 10 dias
    else: return dias, "🟢 NORMAL"            # Acima de 10 dias

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatorio LegalizaHealth', 0, 1, 'C')
        self.ln(5)
def limpar_txt(t):
    if not isinstance(t, str): return str(t)
    return t.replace("✅","").replace("❌","").encode('latin-1','replace').decode('latin-1')
def gerar_pdf(vistorias):
    pdf = PDF()
    pdf.add_page()
    for i, item in enumerate(vistorias):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Item {i+1}: {limpar_txt(item['Item'])}", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 6, f"Local: {limpar_txt(item['Setor'])}\nSituação: {limpar_txt(item['Situação'])}\nObs: {limpar_txt(item['Obs'])}")
        if item['Foto_Binaria']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                t.write(item['Foto_Binaria'].getbuffer())
                pdf.image(t.name, w=60)
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- INTERFACE PRINCIPAL ---

if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []
if 'ultima_notificacao' not in st.session_state: st.session_state['ultima_notificacao'] = datetime.min

# Sidebar
with st.sidebar:
    if img_loading:
        st.markdown(f'<div style="text-
