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

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# SEU CANAL SECRETO DO NTFY
TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"

# --- CONFIGURAÇÃO DOS INTERVALOS DE NOTIFICAÇÃO (EM MINUTOS) ---
INTERVALO_ATRASADO = 10  # A cada 10 minutos
INTERVALO_HOJE = 30      # A cada 30 minutos
INTERVALO_CRITICO = 60   # A cada 1 hora

# Função para carregar imagem
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""

img_loading = get_img_as_base64("loading.gif")

# CSS (Design Tecnológico)
st.markdown(f"""
<style>
    .stApp {{ background-color: #0e1117; color: #e0e0e0; }}
    
    /* Métricas */
    div[data-testid="metric-container"] {{
        background-color: #1f2937; 
        border: 1px solid #374151;
        padding: 15px; border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    
    /* Botões */
    .stButton>button {{
        border-radius: 8px; font-weight: bold; text-transform: uppercase;
        background-image: linear-gradient(to right, #2563eb, #1d4ed8);
        border: none; color: white;
    }}
    
    /* Status Animado */
    @keyframes pulse {{
        0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }}
    }}
    .monitor-ativo {{
        color: #00e676; font-weight: bold; animation: pulse 2s infinite;
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
    """Envia notificação inteligente"""
    
    # Define urgência e ícones
    if dias_restantes < 0:
        prio = "urgent"
        tags = "rotating_light,skull"
        titulo = f"⛔ ATRASADO: {documento}"
        intervalo = INTERVALO_ATRASADO
    elif dias_restantes == 0:
        prio = "high"
        tags = "boom,clock4"
        titulo = f"💥 VENCE HOJE: {documento}"
        intervalo = INTERVALO_HOJE
    elif dias_restantes <= 3:
        prio = "high"
        tags = "warning"
        titulo = f"🚨 URGENTE ({dias_restantes}d): {documento}"
        intervalo = INTERVALO_CRITICO
    else:
        return False # Não notifica se estiver longe

    mensagem = f"Prazo: {data_venc}\nStatus: {status}\n(Alerta repetirá em {intervalo}min)"

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
        if "Concluido" not in df.columns: df["Concluido"] = "False"
        df['Vencimento'] = pd.to_datetime(df['Vencimento'], dayfirst=True, errors='coerce').dt.date
        df['Concluido'] = df['Concluido'].astype(str).str.upper() == 'TRUE'
        return df
    except:
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status", "Concluido"])

def calcular_status(data_venc, concluido):
    if concluido: return 999, "✅ RESOLVIDO"
    if pd.isnull(data_venc): return 0, "⚪ ERRO"
    
    hoje = date.today()
    dias = (data_venc - hoje).days
    
    if dias < 0: return dias, "⛔ ATRASADO"
    elif dias == 0: return dias, "💥 VENCE HOJE"
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

if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []
# Dicionário para controlar quando foi a última notificação de cada item
if 'ultima_notificacao' not in st.session_state: st.session_state['ultima_notificacao'] = {}

with st.sidebar:
    if img_loading:
        st.markdown(f'<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px; margin-bottom:15px;"></div>', unsafe_allow_html=True)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=80)
    
    st.markdown("### LegalizaHealth Pro")
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Gestão de Prazos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")
    
    # --- ROBÔ DE MONITORAMENTO ---
    st.markdown("### 🤖 Robô de Alertas")
    monitorar = st.toggle("Ativar Monitoramento em Tempo Real", value=False)
    
    status_placeholder = st.empty()

# --- LÓGICA DO ROBÔ (Executa se o toggle estiver ligado) ---
if monitorar:
    status_placeholder.markdown('<span class="monitor-ativo">● Monitorando...</span>', unsafe_allow_html=True)
    
    # Carrega dados sem mostrar na tela
    df_robo = carregar_dados_prazos()
    agora = datetime.now()
    
    for index, row in df_robo.iterrows():
        if not row['Concluido']: # Só verifica se não estiver pronto
            dias, status = calcular_status(row['Vencimento'], False)
            
            # Define intervalo baseado na urgência
            intervalo_minutos = None
            if dias < 0: intervalo_minutos = INTERVALO_ATRASADO
            elif dias == 0: intervalo_minutos = INTERVALO_HOJE
            elif dias <= 3: intervalo_minutos = INTERVALO_CRITICO
            
            if intervalo_minutos:
                chave_doc = row['Documento']
                ultima_vez = st.session_state['ultima_notificacao'].get(chave_doc)
                
                # Se nunca mandou OU se já passou o tempo do intervalo
                mandar_agora = False
                if ultima_vez is None:
                    mandar_agora = True
                else:
                    diferenca = (agora - ultima_vez).total_seconds() / 60
                    if diferenca >= intervalo_minutos:
                        mandar_agora = True
                
                if mandar_agora:
                    sucesso = enviar_notificacao_push(row['Documento'], str(row['Vencimento']), dias, status)
                    if sucesso:
                        st.session_state['ultima_notificacao'][chave_doc] = agora
                        st.toast(f"🤖 Alerta enviado: {row['Documento']}")
    
    # Faz o script rodar de novo a cada 30 segundos para checar novamente
    time.sleep(30)
    st.rerun()

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    if not monitorar:
        with st.spinner('Atualizando...'): time.sleep(0.3)
    
    df = carregar_dados_prazos()
    
    criticos_lista = []
    atencao_lista = []
    
    for index, row in df.iterrows():
        d, s = calcular_status(row['Vencimento'], row['Concluido'])
        df.at[index, 'Status'] = s
        
        if not row['Concluido']:
            if "CRÍTICO" in s or "ATRASADO" in s or "VENCE HOJE" in s: criticos_lista.append(row)
            if "ALTA" in s: atencao_lista.append(row)

    n_criticos = len(criticos_lista)
    n_atencao = len(atencao_lista)

    c1, c2, c3 = st.columns(3)
    c1.metric("🚨 Risco Imediato", n_criticos, delta="Ação Necessária" if n_criticos > 0 else "OK", delta_color="inverse")
    c2.metric("🟠 Atenção", n_atencao, delta_color="off")
    c3.metric("📋 Total", len(df))

    st.markdown("---")
    
    if n_criticos > 0:
        st.error(f"⚠️ Atenção! {n_criticos} documentos requerem sua ação.")
        df_criticos = pd.DataFrame(criticos_lista)
        st.dataframe(df_criticos[['Documento', 'Vencimento', 'Status']], use_container_width=True, hide_index=True)
    else:
        st.success("Tudo tranquilo por enquanto.")

# --- 2. GESTÃO DE PRAZOS ---
elif menu == "📅 Gestão de Prazos":
    st.title("Gestão de Documentos")
    
    if 'df_prazos' not in st.session_state: st.session_state['df_prazos'] = carregar_dados_prazos()
    df_editavel = st.session_state['df_prazos']

    df_alterado = st.data_editor(
        df_editavel,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Concluido": st.column_config.CheckboxColumn("✅ Feito?", default=False),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", step=1),
            "Documento": st.column_config.TextColumn("Nome", width="large"),
        },
        key="editor_prazos"
    )

    if st.button("💾 SALVAR ALTERAÇÕES", type="primary", use_container_width=True):
        for index, row in df_alterado.iterrows():
            d, s = calcular_status(row['Vencimento'], row['Concluido'])
            df_alterado.at[index, 'Status'] = s
        
        if sincronizar_prazos_completo(df_alterado):
            st.session_state['df_prazos'] = df_alterado

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
                enviar_notificacao_push(f"VISTORIA: {item}", "HOJE", 0, "PROBLEMA CRÍTICO DETECTADO")

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
