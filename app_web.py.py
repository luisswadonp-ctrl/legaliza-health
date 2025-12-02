import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
import requests

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# SEU CANAL SECRETO DO NTFY
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

# CSS (Dark Mode Ajustado)
st.markdown(f"""
<style>
    .stApp {{ background-color: #0e1117; color: #fafafa; }}
    div[data-testid="metric-container"] {{
        background-color: #262730; border: 1px solid #464b5f;
        padding: 15px; border-radius: 10px;
    }}
    .stButton>button {{
        border-radius: 8px; font-weight: bold; text-transform: uppercase;
    }}
    /* Cores personalizadas para a tabela */
    div[data-testid="stDataFrame"] {{
        border: 1px solid #464b5f; border-radius: 10px;
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

def enviar_notificacao_push(documento, data_venc, dias_restantes, status):
    """
    Envia notificação inteligente baseada na urgência
    """
    prioridade = "default"
    tags = "information_source"
    
    # Define a urgência da notificação
    if dias_restantes < 0:
        prioridade = "urgent" # Toca alarme alto
        tags = "rotating_light,skull"
        titulo = f"⛔ ATRASADO: {documento}"
    elif dias_restantes <= 3:
        prioridade = "high" # Toca e vibra
        tags = "warning,clock4"
        titulo = f"🚨 URGENTE: {documento}"
    else:
        prioridade = "default"
        tags = "calendar"
        titulo = f"📅 Aviso: {documento}"

    mensagem = f"Vence em: {data_venc}\nRestam: {dias_restantes} dias\nStatus: {status}"

    try:
        requests.post(
            f"https://ntfy.sh/{TOPICO_NOTIFICACAO}",
            data=mensagem.encode('utf-8'),
            headers={
                "Title": titulo.encode('utf-8'),
                "Priority": prioridade,
                "Tags": tags
            }
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
        
        # Converte booleanos (True/False) para string para não dar erro no sheets
        df_salvar['Concluido'] = df_salvar['Concluido'].astype(str)
        df_salvar['Vencimento'] = df_salvar['Vencimento'].astype(str)
        
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
        
        # Garante que a coluna Concluido exista
        if "Concluido" not in df.columns:
            df["Concluido"] = "False"
            
        # Converte Data
        df['Vencimento'] = pd.to_datetime(df['Vencimento'], dayfirst=True, errors='coerce').dt.date
        
        # Converte Texto "TRUE"/"FALSE" do Google Sheets para Booleano real
        df['Concluido'] = df['Concluido'].astype(str).str.upper() == 'TRUE'
        
        return df
    except:
        # Cria estrutura vazia se falhar
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status", "Concluido"])

def calcular_status(data_venc, concluido):
    """Calcula cor e texto baseado na data e se já foi feito"""
    if concluido:
        return 999, "✅ RESOLVIDO" # 999 joga pro final da lista se ordenar
    
    if pd.isnull(data_venc): return 0, "⚪ DATA INVÁLIDA"
    
    hoje = date.today()
    dias = (data_venc - hoje).days
    
    if dias < 0: return dias, "⛔ ATRASADO"
    elif dias <= 3: return dias, "🔴 CRÍTICO"
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
        pdf.cell(0, 10, f"Item {i+1}: {limpar_txt(item['Item'])}", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 6, f"Local: {limpar_txt(item['Setor'])}\nSituação: {limpar_txt(item['Situação'])}\nObs: {limpar_txt(item['Obs'])}")
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
    
    st.markdown("### LegalizaHealth Pro")
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Gestão de Prazos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")

if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    with st.spinner('Analisando dados...'):
        time.sleep(0.5)
    
    df = carregar_dados_prazos()
    
    # Lógica de Métricas
    criticos_lista = []
    atencao_lista = []
    
    # Filtra e atualiza
    for index, row in df.iterrows():
        d, s = calcular_status(row['Vencimento'], row['Concluido'])
        df.at[index, 'Status'] = s
        df.at[index, 'Dias'] = d
        
        # Só conta como risco se NÃO estiver concluído
        if not row['Concluido']:
            if "CRÍTICO" in s or "ATRASADO" in s: criticos_lista.append(row)
            if "ALTA" in s: atencao_lista.append(row)

    n_criticos = len(criticos_lista)
    n_atencao = len(atencao_lista)

    c1, c2, c3 = st.columns(3)
    c1.metric("🚨 Prazos Críticos", n_criticos, delta="Ação Imediata" if n_criticos > 0 else "OK", delta_color="inverse")
    c2.metric("🟠 Atenção", n_atencao, delta_color="off")
    c3.metric("📋 Total Monitorado", len(df))

    st.markdown("---")
    
    # Tabela Filtrada
    if n_criticos > 0:
        st.error(f"⚠️ Existem {n_criticos} itens pendentes com risco!")
        df_criticos = pd.DataFrame(criticos_lista)
        # Exibe apenas colunas úteis
        st.dataframe(
            df_criticos[['Documento', 'Vencimento', 'Status']], 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.success("Nenhuma pendência crítica hoje.")

# --- 2. GESTÃO DE PRAZOS (CHECKLIST) ---
elif menu == "📅 Gestão de Prazos":
    st.title("Gestão de Documentos")
    st.caption("Marque a caixa 'Concluído' para remover o alerta de pendência.")
    
    if 'df_prazos' not in st.session_state: 
        st.session_state['df_prazos'] = carregar_dados_prazos()
    
    df_editavel = st.session_state['df_prazos']

    # EDITOR DE DADOS PODEROSO
    df_alterado = st.data_editor(
        df_editavel,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Concluido": st.column_config.CheckboxColumn(
                "Concluído?",
                help="Marque se já resolveu este problema",
                default=False,
            ),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", step=1),
            "Documento": st.column_config.TextColumn("Nome do Documento", width="large"),
        },
        key="editor_prazos"
    )

    if st.button("💾 SALVAR E NOTIFICAR", type="primary", use_container_width=True):
        count_notificacoes = 0
        
        for index, row in df_alterado.iterrows():
            # Recalcula status com base no novo check de concluido
            d, s = calcular_status(row['Vencimento'], row['Concluido'])
            df_alterado.at[index, 'Status'] = s
            
            # NOTIFICAÇÃO INTELIGENTE
            # Só notifica se: É Crítico/Atrasado E NÃO está concluído
            if not row['Concluido'] and ("CRÍTICO" in s or "ATRASADO" in s):
                enviar_notificacao_push(
                    row['Documento'], 
                    str(row['Vencimento']), 
                    d, 
                    s
                )
                count_notificacoes += 1
        
        if sincronizar_prazos_completo(df_alterado):
            st.session_state['df_prazos'] = df_alterado
            st.success("✅ Atualizado!")
            if count_notificacoes > 0:
                st.toast(f"📢 {count_notificacoes} Alertas enviados para o celular!", icon="📲")

# --- 3. VISTORIA ---
elif menu == "📸 Nova Vistoria":
    st.title("Auditoria Mobile")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        c1.write("📷 **Foto**"); foto = c1.camera_input("Capturar")
        c2.write("📝 **Dados**")
        setor = c2.selectbox("Local", ["Recepção", "Raio-X", "UTI", "Expurgo", "Cozinha", "Outros"])
        item = c2.text_input("Item")
        sit = c2.radio("Situação", ["❌ Irregular", "✅ Conforme"], horizontal=True)
        grav = c2.select_slider("Risco", ["Baixo", "Médio", "Alto", "CRÍTICO"])
        obs = c2.text_area("Obs")
        
        if st.button("➕ REGISTRAR", type="primary", use_container_width=True):
            st.session_state['vistorias'].append({"Setor": setor, "Item": item, "Situação": sit, "Gravidade": grav, "Obs": obs, "Foto_Binaria": foto})
            st.success("Registrado!")
            if grav == "CRÍTICO":
                enviar_notificacao_push(f"VISTORIA: {setor}", "HOJE", 0, f"PROBLEMA CRÍTICO: {item}")

# --- 4. RELATÓRIOS ---
elif menu == "📂 Relatórios":
    st.title("Relatórios")
    qtd = len(st.session_state['vistorias'])
    st.metric("Itens Vistoriados", qtd)
    if qtd > 0:
        c1, c2 = st.columns(2)
        if c1.button("☁️ Salvar Nuvem"): salvar_vistoria_db(st.session_state['vistorias']); st.toast("Salvo!")
        pdf = gerar_pdf(st.session_state['vistorias'])
        c2.download_button("📥 Baixar PDF", data=pdf, file_name="Relatorio.pdf", mime="application/pdf", type="primary")
