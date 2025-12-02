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
import streamlit.components.v1 as components
import pytz

# --- 1. CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"
INTERVALO_GERAL = 60 # Minutos para o robô checar

# --- AUTO-REFRESH (Mantém o sistema vivo a cada 60s) ---
components.html("""
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 60000);
</script>
""", height=0)

# --- FUNÇÕES VISUAIS ---
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f: data = f.read()
        return base64.b64encode(data).decode()
    except: return ""

img_loading = get_img_as_base64("loading.gif")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    div[data-testid="metric-container"] {
        background-color: #1f2937; border: 1px solid #374151;
        padding: 15px; border-radius: 10px;
    }
    .stButton>button {
        border-radius: 8px; font-weight: bold; text-transform: uppercase;
        background-image: linear-gradient(to right, #2563eb, #1d4ed8);
        border: none; color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO E DADOS ---

def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

def enviar_resumo_push(lista_problemas):
    qtd = len(lista_problemas)
    if qtd == 0: return False
    
    tem_atrasado = False
    for p in lista_problemas:
        if "ATRASADO" in p['status']:
            tem_atrasado = True
            break
            
    if tem_atrasado:
        titulo = f"⛔ URGENTE: {qtd} Pendências"
        prio = "urgent"; tags = "rotating_light"
    else:
        titulo = f"⚠️ ALERTA: {qtd} Prazos"
        prio = "high"; tags = "warning"

    mensagem = "Resumo:\n"
    for p in lista_problemas[:5]:
        mensagem += f"- {p['doc']} ({p['status']})\n"
    if qtd > 5: mensagem += f"...e mais {qtd-5}."

    try:
        requests.post(f"https://ntfy.sh/{TOPICO_NOTIFICACAO}",
                      data=mensagem.encode('utf-8'),
                      headers={"Title": titulo.encode('utf-8'), "Priority": prio, "Tags": tags})
        return True
    except: return False

def sincronizar_prazos_completo(df_novo):
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        ws.clear()
        
        df_salvar = df_novo.copy()
        df_salvar['Concluido'] = df_salvar['Concluido'].astype(str)
        # Salva data como texto simples para não bugar o sheets
        df_salvar['Vencimento'] = df_salvar['Vencimento'].apply(lambda x: x.strftime('%d/%m/%Y') if hasattr(x, 'strftime') else str(x))
        
        lista = [df_salvar.columns.values.tolist()] + df_salvar.values.tolist()
        ws.update(lista)
        st.toast("✅ Salvo!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro salvar: {e}")
        return False

def salvar_vistoria_db(lista_itens):
    try:
        sh = conectar_gsheets()
        try: ws = sh.worksheet("Vistorias")
        except: ws = sh.add_worksheet(title="Vistorias", rows=1000, cols=10)
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        for item in lista_itens:
            ws.append_row([item['Setor'], item['Item'], item['Situação'], item['Gravidade'], item['Obs'], hoje])
    except: st.error("Erro salvar vistoria.")

def carregar_dados_prazos():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        dados = ws.get_all_records()
        df = pd.DataFrame(dados)
        
        if "Concluido" not in df.columns: df["Concluido"] = "False"
        
        # --- CORREÇÃO DA DATA (O SEGREDO DO SUCESSO) ---
        # 1. Tenta converter DD/MM/AAAA (Brasil)
        # 2. Se falhar, tenta formato padrão
        # 3. dayfirst=True é a chave para 03/12 ser Dezembro
        df['Vencimento'] = pd.to_datetime(df['Vencimento'], dayfirst=True, errors='coerce').dt.date
        
        df['Concluido'] = df['Concluido'].astype(str).str.upper() == 'TRUE'
        return df
    except:
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status", "Concluido"])

def calcular_status(data_venc, concluido):
    if concluido: return 999, "✅ RESOLVIDO"
    if pd.isnull(data_venc): return 0, "⚪ ERRO DATA"
    
    # Usa fuso horário de SP para garantir que "Hoje" é "Hoje no Brasil"
    fuso = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(fuso).date()
    
    dias = (data_venc - hoje).days
    
    if dias < 0: return dias, "⛔ ATRASADO"
    elif dias == 0: return dias, "💥 VENCE HOJE"
    elif dias <= 7: return dias, "🔴 CRÍTICO"
    elif dias <= 10: return dias, "🟠 ALTO"
    else: return dias, "🟢 NORMAL"

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatorio LegalizaHealth', 0, 1, 'C')
        self.ln(5)
def limpar_txt(t):
    return str(t).replace("✅","").replace("❌","").encode('latin-1','replace').decode('latin-1')
def gerar_pdf(vistorias):
    pdf = PDF()
    pdf.add_page()
    for i, item in enumerate(vistorias):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Item {i+1}: {limpar_txt(item['Item'])}", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 6, f"Local: {limpar_txt(item['Setor'])}\nObs: {limpar_txt(item['Obs'])}")
        if item['Foto_Binaria']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                t.write(item['Foto_Binaria'].getbuffer())
                pdf.image(t.name, w=60)
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- 3. INICIALIZAÇÃO ---
if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []
if 'ultima_notificacao' not in st.session_state: st.session_state['ultima_notificacao'] = datetime.min

# --- 4. BARRA LATERAL ---
with st.sidebar:
    if img_loading:
        st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    
    st.markdown("### LegalizaHealth Pro")
    st.caption("v5.1 - Final Fix")
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Gestão de Prazos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")

# --- 5. ROBÔ ---
try:
    agora = datetime.now()
    diff = (agora - st.session_state['ultima_notificacao']).total_seconds() / 60
    
    if diff >= INTERVALO_GERAL:
        df_robo = carregar_dados_prazos()
        lista_notif = []
        for index, row in df_robo.iterrows():
            if not row['Concluido']:
                dias, status = calcular_status(row['Vencimento'], False)
                if isinstance(status, str) and ("CRÍTICO" in status or "ATRASADO" in status or "HOJE" in status or "ALTO" in status):
                    s_limpo = status.replace("🔴 ", "").replace("⛔ ", "").replace("💥 ", "")
                    lista_notif.append({"doc": row['Documento'], "status": s_limpo})
        
        if len(lista_notif) > 0:
            if enviar_resumo_push(lista_notif):
                st.session_state['ultima_notificacao'] = agora
                st.toast(f"🤖 Resumo enviado ({len(lista_notif)} itens)")
except Exception as e:
    print(f"Erro robô: {e}")

# --- 6. TELAS ---

if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    
    # 1. Carrega dados
    df = carregar_dados_prazos()
    
    # 2. Processa TODAS as linhas para garantir que Prazo_Txt exista
    df['Prazo_Txt'] = "" 
    
    criticos_lista = []
    atencao_lista = []

    for index, row in df.iterrows():
        # Calcula status para cada linha
        d, s = calcular_status(row['Vencimento'], row['Concluido'])
        
        # Salva no dataframe
        df.at[index, 'Status'] = s
        
        # Cria texto bonito
        if s == "⚪ ERRO DATA": txt = "---"
        elif d < 0: txt = f"🚨 {abs(d)} dias ATRASO"
        elif d == 0: txt = "💥 VENCE HOJE"
        else: txt = f"{d} dias restantes"
        
        df.at[index, 'Prazo_Txt'] = txt
        
        # Filtra para os contadores
        if not row['Concluido']:
            if isinstance(s, str) and ("CRÍTICO" in s or "ATRASADO" in s or "HOJE" in s): 
                criticos_lista.append(row) # Salva a linha JÁ processada
            if isinstance(s, str) and "ALTO" in s: 
                atencao_lista.append(row)

    # 3. Exibe Métricas
    col1, col2, col3 = st.columns(3)
    col1.metric("🚨 Risco Imediato", len(criticos_lista), delta="Ação" if len(criticos_lista) > 0 else "OK", delta_color="inverse")
    col2.metric("🟠 Prioridade Alta", len(atencao_lista), delta_color="off")
    col3.metric("📋 Total", len(df))
    st.markdown("---")
    
    # 4. Tabela de Alerta
    if len(criticos_lista) > 0:
        st.error(f"⚠️ Atenção! {len(criticos_lista)} documentos requerem sua ação.")
        
        # Converte a lista de linhas de volta para DataFrame para exibir
        df_show = pd.DataFrame(criticos_lista)
        
        # Exibe apenas as colunas úteis (AQUI ESTAVA O PROBLEMA ANTES, AGORA VAI APARECER)
        st.dataframe(
            df_show[['Documento', 'Vencimento', 'Prazo_Txt', 'Status']], 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.success("Tudo tranquilo.")

elif menu == "📅 Gestão de Prazos":
    st.title("Gestão de Documentos")
    st.caption("Datas: Dia/Mês/Ano. Marque 'Feito' para finalizar.")
    
    if 'df_prazos' not in st.session_state: st.session_state['df_prazos'] = carregar_dados_prazos()
    
    df_alterado = st.data_editor(
        st.session_state['df_prazos'],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Concluido": st.column_config.CheckboxColumn("✅ Feito?", default=False),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", step=1),
            "Documento": st.column_config.TextColumn("Nome", width="large"),
        },
        key="editor_prazos"
    )

    if st.button("💾 SALVAR E ATUALIZAR", type="primary", use_container_width=True):
        for index, row in df_alterado.iterrows():
            d, s = calcular_status(row['Vencimento'], row['Concluido'])
            df_alterado.at[index, 'Status'] = s
        
        if sincronizar_prazos_completo(df_alterado):
            st.session_state['df_prazos'] = df_alterado
            st.success("Atualizado!")

elif menu == "📸 Nova Vistoria":
    st.title("Auditoria Mobile")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        foto = c1.camera_input("Foto")
        setor = c2.selectbox("Local", ["Recepção", "Raio-X", "UTI", "Expurgo", "Cozinha", "Outros"])
        item = c2.text_input("Item")
        sit = c2.radio("Situação", ["❌ Irregular", "✅ Conforme"], horizontal=True)
        grav = c2.select_slider("Risco", ["Baixo", "Médio", "Alto", "CRÍTICO"])
        obs = c2.text_area("Obs")
        
        if st.button("➕ REGISTRAR", type="primary", use_container_width=True):
            st.session_state['vistorias'].append({"Setor": setor, "Item": item, "Situação": sit, "Gravidade": grav, "Obs": obs, "Foto_Binaria": foto})
            st.success("Registrado!")

elif menu == "📂 Relatórios":
    st.title("Relatórios")
    qtd = len(st.session_state['vistorias'])
    st.metric("Itens Vistoriados", qtd)
    if qtd > 0:
        c1, c2 = st.columns(2)
        if c1.button("☁️ Salvar Nuvem"): salvar_vistoria_db(st.session_state['vistorias']); st.toast("Salvo!")
        pdf = gerar_pdf(st.session_state['vistorias'])
        c2.download_button("📥 Baixar PDF", data=pdf, file_name="Relatorio.pdf", mime="application/pdf", type="primary")
