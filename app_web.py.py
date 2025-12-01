import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
import requests # <--- NOVA BIBLIOTECA PARA NOTIFICAÇÃO

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# NOME DO CANAL SECRETO (Crie um nome difícil para ninguém adivinhar)
TOPICO_NOTIFICACAO = "legaliza_vida_alerta_secreto_123" 

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
    """Manda notificação direto para o celular via Ntfy"""
    try:
        requests.post(
            f"https://ntfy.sh/{TOPICO_NOTIFICACAO}",
            data=mensagem.encode(encoding='utf-8'),
            headers={
                "Title": titulo.encode(encoding='utf-8'),
                "Priority": "high",
                "Tags": "rotating_light,hospital" # Ícones que aparecem na notificação
            }
        )
        return True
    except Exception as e:
        print(f"Erro push: {e}")
        return False

def sincronizar_prazos_completo(df_novo):
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        ws.clear()
        df_salvar = df_novo.copy()
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
    if pd.isnull(data_venc): return 0, "⚪ ERRO DATA"
    hoje = date.today()
    dias = (data_venc - hoje).days
    if dias <= 3: return dias, "🔴 CRÍTICO"
    elif dias <= 15: return dias, "🟠 ALTA"
    else: return dias, "🟢 NORMAL"

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
        pdf.cell(0, 10, f"#{i+1}: {limpar_txt(item['Item'])}", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 6, f"Local: {limpar_txt(item['Setor'])}\nStatus: {limpar_txt(item['Situação'])} | Risco: {limpar_txt(item['Gravidade'])}\nObs: {limpar_txt(item['Obs'])}")
        if item['Foto_Binaria']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                t.write(item['Foto_Binaria'].getbuffer())
                pdf.image(t.name, w=60)
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- INTERFACE ---

with st.sidebar:
    if img_loading:
        st.markdown(f'<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px; margin-bottom:15px;"></div>', unsafe_allow_html=True)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=80)
    
    st.markdown("### LegalizaHealth")
    st.markdown("---")
    menu = st.radio("Navegação", ["📊 Dashboard", "📅 Gestão de Prazos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")

if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    
    with st.spinner('Sincronizando...'):
        time.sleep(0.5)
    
    df = carregar_dados_prazos()
    
    # Recalcula e Atualiza Status
    criticos_lista = []
    atencao_lista = []
    
    for index, row in df.iterrows():
        d, s = calcular_status_e_cor(row['Vencimento'])
        df.at[index, 'Status'] = s
        df.at[index, 'Dias'] = d
        if "CRÍTICO" in s: criticos_lista.append(row)
        if "ALTA" in s: atencao_lista.append(row)

    n_criticos = len(criticos_lista)
    n_atencao = len(atencao_lista)

    # Métricas
    c1, c2, c3 = st.columns(3)
    c1.metric("🚨 Críticos (< 3 dias)", n_criticos, delta=f"{n_criticos} Urgentíssimos", delta_color="inverse")
    c2.metric("🟠 Atenção (< 15 dias)", n_atencao, delta_color="off")
    c3.metric("📋 Total Documentos", len(df))

    st.markdown("---")

    # Filtros
    with st.expander("🔍 FILTRAR DADOS", expanded=False):
        filtro_status = st.multiselect("Status:", ["🔴 CRÍTICO", "🟠 ALTA", "🟢 NORMAL"], default=["🔴 CRÍTICO"])
        
    df_filtrado = df[df['Status'].isin(filtro_status)] if filtro_status else df

    # Tabela Visual
    def color_coding(val):
        color = '#1b5e20' if val == "🟢 NORMAL" else '#5e451b' if val == "🟠 ALTA" else '#5e1b1b'
        return f'background-color: {color}'

    if not df_filtrado.empty:
        st.dataframe(df_filtrado[['Documento', 'Vencimento', 'Dias', 'Status']].style.applymap(color_coding, subset=['Status']), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum item com este filtro.")
        
    # Botão de Teste de Notificação
    if n_criticos > 0:
        if st.button("🔔 Enviar Notificação de Risco para Celular"):
            enviou = enviar_notificacao_push("ALERTA HOSPITALAR", f"Atenção! Existem {n_criticos} documentos CRÍTICOS vencendo.")
            if enviou: st.success("Notificação enviada!")

# --- GESTÃO DE PRAZOS ---
elif menu == "📅 Gestão de Prazos":
    st.title("Gestão de Documentos")
    
    if 'df_prazos' not in st.session_state: st.session_state['df_prazos'] = carregar_dados_prazos()
    df_editavel = st.session_state['df_prazos']

    df_alterado = st.data_editor(
        df_editavel, num_rows="dynamic", use_container_width=True,
        column_config={
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", step=1),
            "Documento": st.column_config.TextColumn("Nome", width="large"),
        }, key="editor_prazos"
    )

    if st.button("💾 SALVAR E VERIFICAR", type="primary", use_container_width=True):
        novos_criticos = []
        for index, row in df_alterado.iterrows():
            d, s = calcular_status_e_cor(row['Vencimento'])
            df_alterado.at[index, 'Status'] = s
            if s == "🔴 CRÍTICO": novos_criticos.append(row['Documento'])
        
        if sincronizar_prazos_completo(df_alterado):
            st.session_state['df_prazos'] = df_alterado
            st.success("Salvo!")
            
            # NOTIFICAÇÃO AUTOMÁTICA
            if novos_criticos:
                msg = f"URGENTE: {len(novos_criticos)} itens críticos! ({novos_criticos[0]}...)"
                enviar_notificacao_push("🚨 RISCO DETECTADO", msg)
                st.toast("Notificação enviada para o celular!", icon="📲")

# --- VISTORIA ---
elif menu == "📸 Nova Vistoria":
    st.title("Auditoria Mobile")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        c1.write("📷 **Foto**"); foto = c1.camera_input("Capturar")
        c2.write("📝 **Dados**")
        setor = c2.selectbox("Local", ["Recepção", "Raio-X", "UTI", "Expurgo", "Cozinha", "Engenharia"])
        item = c2.text_input("Item")
        sit = c2.radio("Situação", ["❌ Irregular", "✅ Conforme"], horizontal=True)
        grav = c2.select_slider("Risco", ["Baixo", "Médio", "Alto", "CRÍTICO"])
        obs = c2.text_area("Obs")
        
        if st.button("➕ REGISTRAR", type="primary", use_container_width=True):
            st.session_state['vistorias'].append({"Setor": setor, "Item": item, "Situação": sit, "Gravidade": grav, "Obs": obs, "Foto_Binaria": foto})
            st.success("Item salvo!")
            if grav == "CRÍTICO":
                enviar_notificacao_push("VISTORIA CRÍTICA", f"Problema Grave no {setor}: {item}")

# --- RELATÓRIOS ---
elif menu == "📂 Relatórios":
    st.title("Relatórios")
    qtd = len(st.session_state['vistorias'])
    st.metric("Itens Vistoriados", qtd)
    if qtd > 0:
        c1, c2 = st.columns(2)
        if c1.button("☁️ Salvar Drive"): salvar_vistoria_db(st.session_state['vistorias']); st.toast("Salvo!")
        pdf = gerar_pdf(st.session_state['vistorias'])
        c2.download_button("📥 Baixar PDF", data=pdf, file_name="Relatorio.pdf", mime="application/pdf", type="primary")
