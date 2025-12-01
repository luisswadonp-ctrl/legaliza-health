import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
import requests # NOVA IMPORTAÇÃO PARA O PUSH

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# NOME DO CANAL DE NOTIFICAÇÃO (Segredo da Vida)
# Ela deve baixar o app "Ntfy" e se inscrever neste nome exato:
TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"

# Função para carregar imagem
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""

img_loading = get_img_as_base64("loading.gif")

# CSS Profissional (Dark Mode)
st.markdown(f"""
<style>
    .stApp {{ background-color: #0e1117; color: #fafafa; }}
    div[data-testid="metric-container"] {{
        background-color: #262730; border: 1px solid #464b5f;
        padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    .stButton>button {{
        border-radius: 8px; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.5px; transition: 0.3s;
    }}
    .alert-box {{ padding: 15px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; }}
    .alert-red {{ background-color: #3d0c0c; color: #ff9999; border: 1px solid #8a2a2a; }}
    .alert-green {{ background-color: #0c2b0e; color: #99ff99; border: 1px solid #1e5e22; }}
</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO E FUNCIONALIDADES ---

def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

def enviar_notificacao_push(titulo, mensagem):
    """Envia alerta para o app Ntfy no celular"""
    try:
        requests.post(
            f"https://ntfy.sh/{TOPICO_NOTIFICACAO}",
            data=mensagem.encode('utf-8'),
            headers={
                "Title": titulo.encode('utf-8'),
                "Priority": "high",
                "Tags": "rotating_light,hospital"
            }
        )
        return True
    except Exception as e:
        print(f"Erro ao enviar push: {e}")
        return False

def sincronizar_prazos_completo(df_novo):
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        ws.clear()
        df_salvar = df_novo.copy()
        # Garante que as datas sejam salvas como texto para não quebrar
        df_salvar['Vencimento'] = df_salvar['Vencimento'].astype(str)
        lista_dados = [df_salvar.columns.values.tolist()] + df_salvar.values.tolist()
        ws.update(lista_dados)
        st.toast("✅ Nuvem sincronizada!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro sincronização: {e}")
        return False

def salvar_vistoria_db(lista_itens):
    try:
        sh = conectar_gsheets()
        try: ws = sh.worksheet("Vistorias")
        except: ws = sh.add_worksheet(title="Vistorias", rows=1000, cols=10)
        hoje = date.today().strftime("%d/%m/%Y")
        for item in lista_itens:
            ws.append_row([item['Setor'], item['Item'], item['Situação'], item['Gravidade'], item['Obs'], hoje])
    except Exception as e: st.error(f"Erro salvar vistoria: {e}")

def carregar_dados_prazos():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        dados = ws.get_all_records()
        df = pd.DataFrame(dados)
        df['Vencimento'] = pd.to_datetime(df['Vencimento'], dayfirst=True, errors='coerce').dt.date
        return df
    except:
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status"])

def calcular_status_e_cor(data_venc):
    if
