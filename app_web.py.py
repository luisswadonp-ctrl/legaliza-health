import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import base64
import requests
import streamlit.components.v1 as components
import pytz
import io
from streamlit_option_menu import option_menu

# Tenta importar Plotly
try:
    import plotly.express as px
    import plotly.graph_objects as go
    TEM_PLOTLY = True
except ImportError:
    TEM_PLOTLY = False

# --- 1. CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"
INTERVALO_GERAL = 120
ID_PASTA_DRIVE = "1tGVSqvuy6D_FFz6nES90zYRKd0Tmd2wQ"

# --- AUTO-REFRESH ---
components.html("""
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 60000);
</script>
""", height=0)

# --- FUNÇÕES ---
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f: data = f.read()
        return base64.b64encode(data).decode()
    except: return ""

img_loading = get_img_as_base64("loading.gif")

def safe_prog(val):
    try: return max(0, min(100, int(float(val))))
    except: return 0

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    div[data-testid="metric-container"] {
        background-color: #1f2937; border: 1px solid #374151;
        padding: 15px; border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    .stButton>button {
        border-radius: 8px; font-weight: 600; text-transform: uppercase;
        background-image: linear-gradient(to right, #2563eb, #1d4ed8);
        border: none; color: white;
    }
    .stProgress > div > div > div > div { background-color: #00c853; }
    [data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

def get_creds():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

def conectar_gsheets():
    creds = get_creds()
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

def upload_foto_drive(foto_binaria, nome_arquivo):
    if not ID_PASTA_DRIVE: return ""
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': nome_arquivo, 'parents': [ID_PASTA_DRIVE]}
        media = MediaIoBaseUpload(foto_binaria, mimetype='image/jpeg')
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webContentLink').execute()
        return file.get('webContentLink', '')
    except Exception as e:
        st.error(f"Erro Drive: {e}")
        return ""

def enviar_notificacao_push(titulo, mensagem, prioridade="default"):
    try:
        requests.post(f"https://ntfy.sh/{TOPICO_NOTIFICACAO}",
                      data=mensagem.encode('utf-8'),
                      headers={"Title": titulo.encode('utf-8'), "Priority": prioridade, "Tags": "hospital"})
        return True
    except: return False

@st.cache_data(ttl=INTERVALO_GERAL)
def carregar_tudo():
    try:
        sh = conectar_gsheets()
        ws_prazos = sh.worksheet("Prazos")
        df_prazos = pd.DataFrame(ws_prazos.get_all_records())
        try:
            ws_check = sh.worksheet("Checklist_Itens")
            df_check = pd.DataFrame(ws_check.get_all_records())
        except:
            ws_check = sh.add_worksheet("Checklist_Itens", 1000, 5)
            ws_check.append_row(["Documento_Ref", "Tarefa", "Feito"])
            df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])

        colunas = ["Unidade", "Setor", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido"]
        for c in colunas:
            if c not in df_prazos.columns: df_prazos[c] = ""
            
        if not df_prazos.empty:
            df_prazos["Progresso"] = pd.to_numeric(df_prazos["Progresso"], errors='coerce').fillna(0).astype(int)
            
            for col_txt in ['Unidade', 'Setor', 'Documento', 'Status', 'CNPJ']:
                df_prazos[col_txt] = df_prazos[col_txt].astype(str).str.strip()
            
            for c_date in ['Vencimento', 'Data_Recebimento']:
                df_prazos[c_date] = pd.to_datetime(df_prazos[c_date], dayfirst=True, errors='coerce').dt.date
            
            df_prazos = df_prazos[df_prazos['Documento'] != ""]
            df_prazos['ID_UNICO'] = df_prazos['Unidade'] + " - " + df_prazos['Documento']
        
        if df_check.empty: df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])
        else:
            df_check['Documento_Ref'] = df_check['Documento_Ref'].astype(str)
            df_check = df_check[df_check['Tarefa'] != ""]
        
        return df_prazos, df_check
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

def salvar_alteracoes_completo(df_prazos, df_checklist):
    try:
        sh = conectar_gsheets()
        
        # 1. Salvar df_prazos
        ws_prazos = sh.worksheet("Prazos")
        ws_prazos.clear()
        df_p = df_prazos.copy()
        
        if 'ID_UNICO' in df_p.columns: df_p = df_p.drop(columns=['ID_UNICO'])
        
        for c_date in ['Vencimento', 'Data_Recebimento']:
            df_p[c_date] = df_p[c_date].apply(lambda x: x.strftime('%d/%m/%Y') if hasattr(x, 'strftime') else str(x))
            
        df_p['Concluido'] = df_p['Concluido'].astype(str)
        df_p['Progresso'] = df_p['Progresso'].apply(safe_prog)
        
        colunas_ordem = ["Unidade", "Setor", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido"]
        for c in colunas_ordem: 
            if c not in df_p.columns: df_p[c] = ""
        df_p = df_p[colunas_ordem]

        ws_prazos.update([df_p.columns.values.tolist()] + df_p.values.tolist())
        
        # 2. Salvar df_checklist
        ws_check = sh.worksheet("Checklist_Itens")
        ws_check.clear()
        df_c = df_checklist.copy()
        df_c['Feito'] = df_c['Feito'].astype(str)
        ws_check.update([df_c.columns.values.tolist()] + df_c.values.tolist())
        
        st.cache_data.clear() # Limpa o cache para garantir atualização
        st.toast("✅ Salvo!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

def salvar_vistoria_db(lista_itens):
    try:
        sh = conectar_gsheets()
        try: ws = sh.worksheet("Vistorias")
        except: ws = sh.add_worksheet("Vistorias", 1000, 10)
        header = ws.row_values(1)
        if "Foto_Link" not in header: ws.append_row(["Setor", "Item", "Situação", "Gravidade", "Obs", "Data", "Foto_Link"])
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        progresso = st.progress(0, text="Salvando fotos...")
        for i, item in enumerate(lista_itens):
            link_foto = ""
            if item.get('Foto_Binaria'):
                nome_arq = f"Vist_{hoje.replace('/','-')}_{item['Item']}.jpg"
                item['Foto_Binaria'].seek(0)
                link_foto = upload_foto_drive(item['Foto_Binaria'], nome_arq)
            ws.append_row([item['Setor'], item['Item'], item['Situação'], item['Gravidade'], item['Obs'], hoje, link_foto if link_foto else "FALHA_UPLOAD"])
            progresso.progress((i + 1) / len(lista_itens))
        progresso.empty()
        st.toast("✅ Vistoria Registrada!", icon="☁️")
    except Exception as e: st.error(f"Erro: {e}")

def salvar_historico_editado(df_editado, data_selecionada):
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Vistorias")
        todos_dados = pd.DataFrame(ws.get_all_records())
        todos_dados = todos_dados[todos_dados['Data'] != data_selecionada]
        df_editado['Data'] = data_selecionada
        todos_dados = pd.concat([todos_dados, df_editado], ignore_index=True)
        ws.clear()
        ws.update([todos_dados.columns.values.tolist()] + todos_dados.values.tolist())
        st.toast("Histórico Atualizado!")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar histórico: {e}")
        return False

def carregar_historico_vistorias():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Vistorias")
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12); self.cell(0, 10, 'Relatorio LegalizaHealth', 0, 1, 'C'); self.ln(5)
def limpar_txt(t):
    if not isinstance(t, str): t = str(t)
    t = t.replace("✅", "[OK]").replace("❌", "[X]").replace("🚨", "[!]").replace("⚠️", "[!]")
    return t.encode('latin-1', 'replace').decode('latin-1')
def baixar_imagem_url(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200: return io.BytesIO(response.content)
    except: pass
    return None
def gerar_pdf(vistorias):
    pdf = PDF()
    pdf.add_page()
    for i, item in enumerate(vistorias):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Item #{i+1}: {limpar_txt(item.get('Item', ''))}", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 6, f"Local: {limpar_txt(item.get('Setor',''))}\nObs: {limpar_txt(item.get('Obs',''))}")
        img = None
        if 'Foto_Binaria' in item and item['Foto_Binaria']: img = item['Foto_Binaria']
        elif 'Foto_Link' in item and str(item['Foto_Link']).startswith('http'): img = baixar_imagem_url(item['Foto_Link'])
        if img:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                    t.write(img.getvalue() if hasattr(img, 'getvalue') else img.read())
                    pdf.image(t.name, x=10, w=80)
            except: pass
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- INTERFACE ---
if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []
if 'ultima_notificacao' not in st.session_state: st.session_state['ultima_notificacao'] = datetime.min
if 'doc_focado_id' not in st.session_state: st.session_state['doc_focado_id'] = None
if 'filtro_dash' not in st.session_state: st.session_state['filtro_dash'] = "TODOS"

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    
    menu = option_menu(
        menu_title=None,
        options=["Painel Geral", "Gestão de Docs", "Vistoria Mobile", "Relatórios"],
        icons=["speedometer2", "folder-check", "camera-fill", "file-pdf"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#00c853", "font-size": "18px"},
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"5px", "--hover-color": "#262730"},
            "nav-link-selected": {"background-color": "#1f2937"},
        }
    )
    
    st.markdown("---")
    st.caption("v32.2 - Correção Importação")

# --- ROBÔ ---
try:
    agora = datetime.now()
    diff = (agora - st.session_state['ultima_notificacao']).total_seconds() / 60
    # Usa a versão em cache para evitar leituras excessivas
    df_alertas = carregar_tudo()[0] if diff >= INTERVALO_GERAL else st.session_state.get('dados_cache', [None])[0]
    
    if df_alertas is not None and diff >= INTERVALO_GERAL:
        lista_alerta = []
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date()
        for index, row in df_alertas.iterrows():
            try:
                dias = (row['Vencimento'] - hoje).days
                prog = safe_prog(row['Progresso'])
                if dias < 0 and prog < 100: lista_alerta.append(f"⛔ ATRASADO: {row['Documento']}")
                elif dias <= 5 and prog < 100: lista_alerta.append(f"⚠️ VENCE EM {dias} DIAS: {row['Documento']}")
            except: pass
        if lista_alerta:
            msg = "\n".join(lista_alerta[:5])
            if len(lista_alerta) > 5: msg += "\n..."
            enviar_notificacao_push(f"🚨 ALERTAS", msg, "high")
            st.session_state['ultima_notificacao'] = agora
            st.toast("🤖 Alertas enviados!")
except: pass

# --- TELAS ---

if menu == "Painel Geral":
    st.title("Painel de Controle Estratégico")
    df_p, _ = carregar_tudo() # Usa a função em cache
    
    if df_p.empty:
        st.warning("Ainda não há documentos cadastrados. Adicione na aba 'Gestão de Docs'.")
        st.stop()

    n_crit = len(df_p[df_p['Status'] == "CRÍTICO"])
    n_alto = len(df_p[df_p['Status'] == "ALTO"])
    n_norm = len(df_p[df_p['Status'] == "NORMAL"])
    
    # LAYOUT MOBILE: KPIs empilhados, Tabela e Gráfico empilhados.
    
    c1, c2, c3, c4 = st.columns(4)
    if c1.button(f"🔴 CRÍTICO: {n_crit}", use_container_width=True): st.session_state['filtro_dash'] = "CRÍTICO"
    if c2.button(f"🟠 ALTO: {n_alto}", use_container_width=True): st.session_state['filtro_dash'] = "ALTO"
    if c3.button(f"🟢 NORMAL: {n_norm}", use_container_width=True): st.session_state['filtro_dash'] = "NORMAL"
    if c4.button(f"📋 TOTAL: {len(df_p)}", use_container_width=True): st.session_state['filtro_dash'] = "TODOS"
    
    st.markdown("---")
    
    # 1. TABELA DE ALERTA
    f_atual = st.session_state['filtro_dash']
    st.subheader(f"Lista de Processos: {f_atual}")
    df_show = df_p.copy()
    if f_atual != "TODOS":
        df_show = df_show[df_show['Status'] == f_atual]
        
    if not df_show.empty:
        st.dataframe(
            df_show[['Unidade', 'Setor', 'Documento', 'Vencimento', 'Progresso', 'Status']], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Vencimento": st.column_config.DateColumn("Prazo", format="DD/MM/YYYY"),
                "Progresso": st.column_config.ProgressColumn("Progressão", format="%d%%"),
                "Status": st.column_config.TextColumn("Risco", width="small")
            }
        )
    else:
        st.info("Nenhum item neste status.")

    st.markdown("---")
    
    # 2. GRÁFICO
    st.subheader("Panorama")
    if not df_p.empty and TEM_PLOTLY:
        status_counts = df_p['Status'].value_counts()
        fig = px.pie(values=status_counts.values, names=status_counts.index, hole=0.6,
             color=status_counts.index, color_discrete_map={"CRÍTICO": "#ff4b4b", "ALTO": "#ffa726", "NORMAL": "#00c853"})
        fig.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)
        
        media = int(df_p['Progresso'].mean()) if not df_p.empty else 0
        st.metric("Progressão Geral", f"{media}%")
        st.progress(media)

elif menu == "Gestão de Docs":
    st.title("Gestão de Documentos")
    df_prazos, df_checklist = carregar_tudo() # Carrega com cache
    
    with st.expander("🔍 FILTROS", expanded=True):
        f1, f2, f3 = st.columns(3)
        lista_uni = ["Todas"] + sorted(list(df_prazos['Unidade'].unique())) if 'Unidade' in df_prazos.columns else ["Todas"]
        f_uni = f1.selectbox("Unidade:", lista_uni)
        f_stt = f2.multiselect("Status:", ["CRÍTICO", "ALTO", "NORMAL"])
        f_txt = f3.text_input("Buscar (Nome/CNPJ/Setor):")
        if st.button("Limpar"): st.rerun()

    df_show = df_prazos.copy()
    if f_uni != "Todas": df_show = df_show[df_show['Unidade'] == f_uni]
    if f_stt: df_show = df_show[df_show['Status'].isin(f_stt)]
    if f_txt: df_show = df_show[df_show.astype(str).apply(lambda x: x.str.contains(f_txt, case=False)).any(axis=1)]

    col_l
