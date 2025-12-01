import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# Função para carregar imagem (Suporta GIF e PNG)
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""

# Tenta carregar o loading.gif
img_loading = get_img_as_base64("loading.gif")

# CSS Profissional (Modo Escuro / Dark Mode)
st.markdown(f"""
<style>
    /* Fundo Escuro Profissional (Padrão Streamlit) */
    .stApp {{
        background-color: #0e1117;
        color: #fafafa;
    }}
    
    /* Cartões de Métricas (Escuros) */
    div[data-testid="metric-container"] {{
        background-color: #262730;
        border: 1px solid #464b5f;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    
    /* Botões Modernos */
    .stButton>button {{
        border-radius: 8px;
        font-weight: 600;
        height: 3em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        background-color: #ff4b4b; /* Vermelho destaque */
        color: white;
        border: none;
    }}
    
    /* Ajuste de Texto */
    h1, h2, h3 {{
        font-family: 'Segoe UI', sans-serif;
        color: #ffffff !important;
    }}
    
    /* Mensagens de Alerta Personalizadas (Dark Mode) */
    .alert-box {{
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        font-weight: bold;
    }}
    .alert-red {{ 
        background-color: #3d0c0c; 
        color: #ff9999; 
        border: 1px solid #8a2a2a; 
    }}
    .alert-green {{ 
        background-color: #0c2b0e; 
        color: #99ff99; 
        border: 1px solid #1e5e22; 
    }}

</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO GOOGLE SHEETS ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

# --- 3. LÓGICA DE NEGÓCIO ---

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
        # Converte a coluna de texto para DATA real do Python
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
        pdf.multi_cell(0, 6, f"Setor: {limpar_txt(item['Setor'])}\nStatus: {limpar_txt(item['Situação'])} | Gravidade: {limpar_txt(item['Gravidade'])}\nObs: {limpar_txt(item['Obs'])}")
        if item['Foto_Binaria']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                t.write(item['Foto_Binaria'].getbuffer())
                pdf.image(t.name, w=60)
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- 4. INTERFACE ---

# Sidebar com "Loading" Animado (GIF)
with st.sidebar:
    if img_loading:
        st.markdown(f'<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px; margin-bottom:15px;"></div>', unsafe_allow_html=True)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=80)
    
    st.markdown("### LegalizaHealth")
    st.caption("Gestão de Conformidade Hospitalar")
    st.markdown("---")
    menu = st.radio("Menu", ["📊 Dashboard & Alertas", "📅 Gestão de Prazos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")
    st.info("💡 **Dica:** O sistema salva tudo automaticamente no Google Sheets.")

if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []

# --- DASHBOARD ---
if menu == "📊 Dashboard & Alertas":
    st.title("Painel de Controle")
    
    # Simula um loading rápido com o GIF do sidebar já rodando
    with st.spinner('Sincronizando nuvem...'):
        time.sleep(0.5)
    
    df = carregar_dados_prazos()
    
    criticos_lista = []
    atencao_lista = []
    
    for index, row in df.iterrows():
        d, s = calcular_status_e_cor(row['Vencimento'])
        if "CRÍTICO" in s: criticos_lista.append(row)
        if "ALTA" in s: atencao_lista.append(row)

    n_criticos = len(criticos_lista)
    n_atencao = len(atencao_lista)

    col1, col2, col3 = st.columns(3)
    col1.metric("Prazos Críticos (< 3 dias)", n_criticos, 
                delta=f"{n_criticos} Urgentíssimos" if n_criticos > 0 else "Tudo em ordem", 
                delta_color="inverse") 
    col2.metric("Atenção (< 15 dias)", n_atencao, delta_color="off")
    col3.metric("Total Documentos", len(df))

    st.markdown("---")

    if n_criticos > 0:
        st.markdown(f"""<div class="alert-box alert-red">⚠️ AÇÃO IMEDIATA: Existem {n_criticos} itens vencendo!</div>""", unsafe_allow_html=True)
        st.subheader("🚨 Lista de Prioridade Extrema")
        df_criticos = pd.DataFrame(criticos_lista)
        st.dataframe(df_criticos[['Documento', 'Vencimento', 'Status']], use_container_width=True, hide_index=True)
        if st.button("📧 Enviar Alerta por E-mail"):
            st.toast("E-mail de alerta enviado!", icon="📩")
            
    elif n_atencao > 0:
        st.markdown(f"""<div class="alert-box alert-green">✅ Nenhum item crítico no momento.</div>""", unsafe_allow_html=True)
    else:
        st.balloons()
        st.success("Tudo 100% regularizado.")

# --- GESTÃO DE PRAZOS ---
elif menu == "📅 Gestão de Prazos":
    st.title("Gestão de Documentos")
    
    if 'df_prazos' not in st.session_state:
        st.session_state['df_prazos'] = carregar_dados_prazos()

    df_editavel = st.session_state['df_prazos']

    st.caption("Clique na data para abrir o calendário. Selecione a linha e aperte 'Del' para excluir.")
    
    df_alterado = st.data_editor(
        df_editavel,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Status": st.column_config.TextColumn("Situação", disabled=True),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", step=1),
            "Documento": st.column_config.TextColumn("Nome do Documento", width="large"),
        },
        key="editor_prazos"
    )

    if st.button("💾 Salvar Alterações na Nuvem", type="primary"):
        for index, row in df_alterado.iterrows():
            d, s = calcular_status_e_cor(row['Vencimento'])
            df_alterado.at[index, 'Status'] = s
        
        if sincronizar_prazos_completo(df_alterado):
            st.session_state['df_prazos'] = df_alterado
            st.success("Base de dados atualizada!")

# --- VISTORIA ---
elif menu == "📸 Nova Vistoria":
    st.title("Auditoria Mobile")
    
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write("📷 **Evidência**")
            foto = st.camera_input("Capturar")
        with c2:
            st.write("📝 **Dados**")
            setor = st.selectbox("Local", ["Recepção", "Raio-X", "UTI", "Expurgo", "Cozinha", "Engenharia", "Outros"])
            item = st.text_input("Item", placeholder="Ex: Extintor Vencido")
            
            cc1, cc2 = st.columns(2)
            sit = cc1.radio("Situação", ["❌ Irregular", "✅ Conforme"], horizontal=True)
            grav = cc2.select_slider("Risco", ["Baixo", "Médio", "Alto", "CRÍTICO"])
            
            obs = st.text_area("Obs")
            
            if st.button("➕ Adicionar à Lista", type="primary", use_container_width=True):
                if item:
                    st.session_state['vistorias'].append({
                        "Setor": setor, "Item": item, "Situação": sit,
                        "Gravidade": grav, "Obs": obs, "Foto_Binaria": foto
                    })
                    st.toast("Item registrado!", icon="✅")
                else:
                    st.warning("Descreva o item.")

# --- RELATÓRIOS ---
elif menu == "📂 Relatórios":
    st.title("Central de Relatórios")
    qtd = len(st.session_state['vistorias'])
    st.metric("Itens Vistoriados Hoje", qtd)
    
    if qtd > 0:
        st.markdown("### Prévia")
        for item in st.session_state['vistorias']:
            with st.expander(f"{item['Situação']} {item['Item']} ({item['Setor']})"):
                st.write(item['Obs'])
                if item['Foto_Binaria']: st.image(item['Foto_Binaria'], width=200)

        col1, col2 = st.columns(2)
        with col1:
             if st.button("☁️ Salvar Histórico no Drive"):
                salvar_vistoria_db(st.session_state['vistorias'])
                st.success("Salvo na nuvem!")
        with col2:
            pdf = gerar_pdf(st.session_state['vistorias'])
            st.download_button("📥 Baixar PDF Final", data=pdf, file_name=f"Relatorio_{date.today()}.pdf", mime="application/pdf", type="primary")
    else:
        st.info("Inicie uma vistoria para gerar relatórios.")
