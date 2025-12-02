import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
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
INTERVALO_CHECK_ROBO = 60 # O robô verifica a cada 60 segundos se deu a hora de enviar
ID_PASTA_DRIVE = "1tGVSqvuy6D_FFz6nES90zYRKd0Tmd2wQ"

# --- LISTA PADRÃO DE DOCUMENTOS ---
LISTA_TIPOS_DOCUMENTOS = [
    "Licença de Publicidade", "Conselho de Medicina (CRM)", "Conselho de Farmácia (CRF)", "Licença Sanitária",
    "Conselho de Enfermagem (COREN)", "CNES", "Inscrição Municipal", "Licença Ambiental", "Alvará de Funcionamento",
    "Corpo de Bombeiros", "Polícia Civil (Termo de Vistoria)", "Polícia Civil (Licença)", "Conselho de Biomedicina (CRBM)",
    "Conselho de Biologia (CRBio)", "Conselho de Biomedicina (CRBM) Serviço - Laboratório", "Licença Sanitária Serviço (Laboratório)",
    "Conselho de Biomedicina (CRBM) Serviço - Posto de Coleta", "Licença Sanitária Serviço (Dispensário)", "Conselho de Nutrição (CRN)",
    "Conselho de Psicologia (CRP)", "Licença Sanitária Serviço (Farmácia)", "Conselho de Radiologia (CRTR)",
    "Conselho de Fisioterapia e Terapia Ocupacional (CREFITO)", "Licença Sanitária Serviço (Cozinha/Nutrição)",
    "Licença Sanitária Serviço (Radiologia)", "Conselho de Fonoaudiologia (CREFONO)", "Licença Sanitária Serviço (Oncologia)",
    "Licença Sanitária Serviço (Equipamento)", "Licença Sanitária Serviço (Ag. Transfusional)", "Licença Sanitária Serviço (Clínica)",
    "Conselho de Medicina (CRM) Serviço (Oncologia)", "Conselho de Medicina (CRM) Serviço (Radiologia Clinica)",
    "Conselho de Medicina (CRM) Serviço (Banco de Sangue)", "Conselho de Enfermagem (COREN) Serviço (Urgência/Emergência)",
    "Licença Sanitária Serviço (Vacinas)", "Licença Sanitária Serviço (Quimioterapia)", "Conselho de Enfermagem (COREN) Serviço (Oncologia)",
    "Licença Sanitária Serviço (Equipamento 1)", "Licença Sanitária Serviço (Equipamento 3)", "Licença Sanitária Serviço (Equipamento 5)",
    "Licença Sanitária Serviço (Equipamento 4)", "Licença Sanitária Serviço (Equipamento 2)", "Conselho de Enfermagem (COREN) Serviço (Quimioterapia)",
    "Conselho de Farmácia (CRF) Serviço (Oncologia)", "Licença Sanitária Serviço (Ultrassom)", "Licença Sanitária Serviço (SADT - Apoio Diagnóstico Terapêutico)",
    "Licença Sanitária Serviço (Equipamento 6)", "Declaração de Trâmite Vigilância", "Licença do Comando da Aeronáutica (COMAER)",
    "Certificado de Manutenção do Sistema de Segurança", "Conselho de Odontologia (CRO)", "Licença Sanitária Serviço (Hemoterapia)",
    "Licença Sanitária Serviço (Transplante Musculo Esquelético)", "Licença Sanitária Serviço (Hemodinâmica)", "Conselho de Farmácia (CRF) Serviço - Laboratório",
    "Conselho de Medicina (CRM) Serviço (Endoscopia)", "Conselho de Medicina (CRM) Serviço (UTI Adulto)", "Conselho de Medicina (CRM) Serviço (UTI Neonatal)",
    "Conselho de Medicina (CRM) Serviço Hemodiálise", "Conselho de Medicina (CRM) Serviço (UTI Pediátrica)", "Conselho de Enfermagem (COREN) Serviço (Nefrologia)",
    "Conselho de Enfermagem (COREN) Serviço (UTI Neonatal)", "Conselho de Enfermagem (COREN) Serviço (UTI Adulto 2)",
    "Conselho de Enfermagem (COREN) Serviço (UTI Adulto 3)", "Conselho de Enfermagem (COREN) Serviço (UTI Pediátrica)",
    "Conselho de Enfermagem (COREN) Serviço (UTI Adulto 1)", "Conselho de Enfermagem (COREN) Serviço (Vida & Imagem)",
    "Carta de anuência tombamento", "Licença Sanitária Serviço (Fisioterapia)", "Licença Sanitária Serviço (Assistência Domiciliar)",
    "Conselho de Medicina (CRM) Serviço (Ergometria)", "Certificado de acessibilidade", "Conselho de Farmácia (CRF) Serviço - Farmácia de Manipulação",
    "Licença Sanitária (Tomografia)", "Licença Sanitária Serviço (Transplante de Fígado)", "Conselho de Enfermagem (COREN) Serviço - Hemodinâmica",
    "Polícia Federal (Licença)", "Conselho de Medicina (CRM) Serviço Hemodinamica", "Conselho de Farmácia (CRF) Serviço - Farmácia Hospitalar",
    "Licença Sanitária Serviço (Equipamento 9)", "Licença Sanitária Serviço (Equipamento 7)", "Licença Sanitária Serviço (Equipamento 8)",
    "Licença Sanitária Serviço (Equipamento 15)", "Termo de aceite de sinalização de vaga para deficiente e idoso", "Licença Sanitária Serviço (Equipamento 21)",
    "Licença Sanitária Serviço (Equipamento 18)", "Licença Sanitária Serviço (Equipamento 19)", "Licença Sanitária Serviço (Hemodiálise)",
    "Licença Sanitária Serviço (Transplante de Medula Óssea)", "Cadastro de tanques, bombas e equipamentos afins", "Licença Sanitária Serviço (Equipamento 22)",
    "Licença Sanitária Serviço (Equipamento 11)", "Licença Sanitária Serviço (Equipamento 17)", "Licença Sanitária Serviço (Equipamento 13)",
    "Licença Sanitária Serviço (Equipamento 10)", "Licença Sanitária Serviço (Equipamento 16)", "Licença Sanitária Serviço (Equipamento 12)",
    "Licença Sanitária Serviço (Transplante de Rim)", "Licença Sanitária Serviço (Equipamento 14)", "Licença Sanitária Serviço (Equipamento 20)",
    "Licença Sanitária Serviço (Ambulância)", "Licença Sanitária Serviço (Captação)", "Licença Sanitária Serviço (Registro gráfico, ECG. EEG)",
    "Licença Sanitária Serviço (Tomografia)", "Conselho de Farmácia (CRF) Serviço - Posto de Coleta", "Licença Sanitária Serviço (Remoção de pacientes)",
    "Licença Sanitária Serviço (Endoscopia)", "Licença Sanitária Serviço (Pronto Socorro)", "Conselho de Enfermagem (COREN) Serviço (Ambulatorial)",
    "Conselho de Biomedicina (CRBM) Serviço - Banco de Sangue", "Conselho de Enfermagem (COREN) Serviço (CME)", "Conselho de Enfermagem (COREN) Serviço (UTI)",
    "Conselho de Medicina (CRM) Serviço (Transplante de Médula Óssea)", "Licença Sanitária Serviço (UTI Adulto)", "Conselho de Medicina (CRM) Serviço (Obstetrícia)",
    "Licença Sanitária Serviço (UTI Neonatal)", "Licença Sanitária Serviço (Posto de Coleta de Leite Humano)", "Conselho de Medicina (CRM) Serviço (Neonatologia)",
    "Conselho de Medicina (CRM) Serviço (TME - Transplante de Músculo Esquelético)", "Conselho de Enfermagem (COREN) Serviço (Centro Cirúrgico)",
    "Conselho de Enfermagem (COREN) Serviço (Internação)", "Conselho de Enfermagem (COREN) Serviço (Maternidade)", "Licença Sanitária Serviço (Fonoaudiologia)",
    "Licença Sanitária Serviço (Psicologia)", "Licença Sanitária Serviço (Procedimentos Cirúrgicos)", "Licença Sanitária Serviço (Consultório Isolado)",
    "Conselho de Medicina (CRM) Serviço (Emergência)", "Conselho de Medicina (CRM) Serviço (Pediatria)", "Conselho de Medicina (CRM) - Diálise",
    "Licença Sanitária Serviço (UTI Mista)", "Projeto Arquitetonico (Visa e Prefeitura)", "Habite-se", "SDR", "SMOP", "Alvará de Obra", "Outros"
]
LISTA_TIPOS_DOCUMENTOS = sorted(list(set(LISTA_TIPOS_DOCUMENTOS)))

# --- AUTO-REFRESH ---
components.html("""
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 300000); 
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
    div[data-testid="stButton"] > button[kind="primary"] {
        border: 2px solid #00e676;
        box-shadow: 0 0 10px rgba(0, 230, 118, 0.5);
    }
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

@st.cache_data(ttl=60) # Cache de 1 min para leitura inicial
def carregar_tudo_inicial():
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
            
            df_prazos = df_prazos[df_prazos['Unidade'] != ""]
            df_prazos['ID_UNICO'] = df_prazos['Unidade'] + " - " + df_prazos['Documento']
        
        if df_check.empty: df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])
        else:
            df_check['Documento_Ref'] = df_check['Documento_Ref'].astype(str)
            df_check = df_check[df_check['Tarefa'] != ""]
        
        return df_prazos, df_check
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

def get_dados():
    if 'dados_cache' not in st.session_state or st.session_state['dados_cache'] is None:
        st.session_state['dados_cache'] = carregar_tudo_inicial()
    return st.session_state['dados_cache']

def update_dados_local(df_p, df_c):
    st.session_state['dados_cache'] = (df_p, df_c)

def salvar_alteracoes_completo(df_prazos, df_checklist):
    try:
        sh = conectar_gsheets()
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
        
        ws_check = sh.worksheet("Checklist_Itens")
        ws_check.clear()
        df_c = df_checklist.copy()
        df_c['Feito'] = df_c['Feito'].astype(str)
        ws_check.update([df_c.columns.values.tolist()] + df_c.values.tolist())
        
        st.cache_data.clear()
        st.session_state['dados_cache'] = (df_prazos, df_checklist)
        st.toast("✅ Dados Sincronizados com a Nuvem!", icon="☁️")
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
# --- CONTROLE DOS TIMERS DE NOTIFICAÇÃO ---
if 'last_notify_critico' not in st.session_state: st.session_state['last_notify_critico'] = datetime.min
if 'last_notify_alto' not in st.session_state: st.session_state['last_notify_alto'] = datetime.min

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
    st.caption("v36.0 - Robô Inteligente")

# --- ROBÔ INTELIGENTE V2 ---
try:
    agora = datetime.now()
    
    # Verifica Timers
    diff_crit = (agora - st.session_state['last_notify_critico']).total_seconds() / 60
    diff_alto = (agora - st.session_state['last_notify_alto']).total_seconds() / 60
    
    # Carrega dados
    df_alertas = get_dados()[0]
    
    if df_alertas is not None:
        msgs_crit = []
        msgs_alto = []
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date()
        
        for index, row in df_alertas.iterrows():
            try:
                # 1. FILTRO: Ignora não editados (Pendentes/Selecione) e Normais
                doc_nome = str(row['Documento'])
                if "SELECIONE" in doc_nome or "PENDENTE" in doc_nome: continue
                if row['Status'] == "NORMAL": continue
                
                # 2. FILTRO: Ignora Concluídos (Progresso 100%)
                prog = safe_prog(row['Progresso'])
                if prog >= 100: continue

                dias = (row['Vencimento'] - hoje).days
                unidade = row['Unidade']
                risco = row['Status']
                
                # Monta mensagem
                msg = f"🏥 {unidade}\n📄 {doc_nome}\n⏳ Vence em {dias} dias"
                
                # 3. Lógica de Agrupamento
                if risco == "CRÍTICO" and (dias <= 5 or dias < 0):
                    msgs_crit.append(msg)
                elif risco == "ALTO" and (dias <= 5 or dias < 0):
                    msgs_alto.append(msg)
                    
            except: pass
        
        # 4. ENVIO CONDICIONAL POR TIMER
        # CRÍTICO (A cada 60 min)
        if msgs_crit and diff_crit >= 60:
            corpo = "\n----------------\n".join(msgs_crit[:10]) # Limita a 10 para não explodir
            if len(msgs_crit) > 10: corpo += f"\n... e mais {len(msgs_crit)-10} itens."
            if enviar_notificacao_push("🚨 ALERTA CRÍTICO (1h)", corpo, "high"):
                st.session_state['last_notify_critico'] = agora
        
        # ALTO (A cada 180 min / 3h)
        if msgs_alto and diff_alto >= 180:
            corpo = "\n----------------\n".join(msgs_alto[:10])
            if len(msgs_alto) > 10: corpo += f"\n... e mais {len(msgs_alto)-10} itens."
            if enviar_notificacao_push("🟠 ALERTA ALTO (3h)", corpo, "default"):
                st.session_state['last_notify_alto'] = agora

except Exception as e: pass

# --- TELAS ---

if menu == "Painel Geral":
    st.title("Painel de Controle Estratégico")
    df_p, _ = get_dados()
    
    if df_p.empty:
        st.warning("Ainda não há documentos cadastrados. Adicione na aba 'Gestão de Docs'.")
        st.stop()

    n_crit = len(df_p[df_p['Status'] == "CRÍTICO"])
    n_alto = len(df_p[df_p['Status'] == "ALTO"])
    n_norm = len(df_p[df_p['Status'] == "NORMAL"])
    
    c1, c2, c3, c4 = st.columns(4)
    if c1.button(f"🔴 CRÍTICO: {n_crit}", use_container_width=True): st.session_state['filtro_dash'] = "CRÍTICO"
    if c2.button(f"🟠 ALTO: {n_alto}", use_container_width=True): st.session_state['filtro_dash'] = "ALTO"
    if c3.button(f"🟢 NORMAL: {n_norm}", use_container_width=True): st.session_state['filtro_dash'] = "NORMAL"
    if c4.button(f"📋 TOTAL: {len(df_p)}", use_container_width=True): st.session_state['filtro_dash'] = "TODOS"
    
    st.markdown("---")
    
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
    df_prazos, df_checklist = get_dados()
    
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

    col_l, col_d = st.columns([1.2, 2])

    with col_l:
        st.info(f"Lista ({len(df_show)})")
        sel = st.dataframe(
            df_show[['Unidade', 'Documento', 'Status']], 
            use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun",
            column_config={"Status": st.column_config.TextColumn("Risco", width="small")}
        )
        
        if len(sel.selection.rows) > 0:
            idx_real = sel.selection.rows[0]
            doc_selecionado_id = df_show.iloc[idx_real]['ID_UNICO']
            st.session_state['doc_focado_id'] = doc_selecionado_id
        
        doc_ativo_id = st.session_state.get('doc_focado_id')
        
        st.markdown("---")
        with st.expander("➕ Novo Documento (Manual)"):
            with st.form("new_doc", clear_on_submit=True):
                n_u = st.text_input("Unidade"); n_s = st.text_input("Setor"); n_d = st.selectbox("Documento", options=LISTA_TIPOS_DOCUMENTOS); n_c = st.text_input("CNPJ")
                if st.form_submit_button("ADICIONAR"):
                    if n_u and n_d and n_c:
                        novo = {"Unidade": n_u, "Setor": n_s, "Documento": n_d, "CNPJ": n_c, "Data_Recebimento": date.today(), "Vencimento": date.today(), "Status": "NORMAL", "Progresso": 0, "Concluido": "False"}
                        df_temp = pd.concat([pd.DataFrame([novo]), df_prazos], ignore_index=True)
                        df_temp['ID_UNICO'] = df_temp['Unidade'] + " - " + df_temp['Documento']
                        update_dados_local(df_temp, df_checklist)
                        st.toast("Documento criado! Não esqueça de Salvar na Nuvem.", icon="💾")
                        st.rerun()
                    else:
                        st.error("Preencha Unidade, Documento e CNPJ para adicionar.")

        st.markdown("---")
        with st.expander("⬆️ Importar Unidades/CNPJ (Excel/CSV)"):
            import_file = st.file_uploader("Carregar arquivo (.xlsx ou .csv)", type=['xlsx', 'csv'], key="uploader_import_mass")
            
            if import_file:
                df_novo = pd.DataFrame()
                try:
                    try: df_novo = pd.read_excel(import_file)
                    except:
                        import_file.seek(0)
                        try: df_novo = pd.read_csv(import_file, sep=';', encoding='latin-1')
                        except: 
                            import_file.seek(0)
                            df_novo = pd.read_csv(import_file, sep=',', encoding='utf-8')
                    
                    if not df_novo.empty:
                        df_novo.columns = df_novo.columns.str.strip()
                        if 'Nome da unidade' in df_novo.columns and 'CNPJ' in df_novo.columns:
                            df_import = df_novo[['Nome da unidade', 'CNPJ']].copy()
                            df_import = df_import.rename(columns={'Nome da unidade': 'Unidade'})
                            
                            st.write("### 🔎 Pré-visualização:")
                            st.dataframe(df_import.head(5), use_container_width=True)
                            
                            if st.button(f"✅ Confirmar Importação", type="primary"):
                                df_import['Setor'] = ""
                                df_import['Documento'] = "⚠️ SELECIONE O TIPO"
                                df_import['Data_Recebimento'] = date.today()
                                df_import['Vencimento'] = date.today()
                                df_import['Status'] = "NORMAL"
                                df_import['Progresso'] = 0
                                df_import['Concluido'] = "False"
                                df_import['Unidade'] = df_import['Unidade'].astype(str)
                                df_import['CNPJ'] = df_import['CNPJ'].astype(str)
                                df_import['ID_UNICO'] = df_import['Unidade'] + " - " + df_import['CNPJ'] + " - " + df_import['Documento']
                                
                                df_combinado = pd.concat([df_prazos, df_import], ignore_index=True)
                                df_combinado = df_combinado.drop_duplicates(subset=['ID_UNICO'], keep='last').reset_index(drop=True)
                                
                                salvar_alteracoes_completo(df_combinado, df_checklist)
                                st.success(f"✅ {len(df_import)} importados! Defina os tipos de documento agora.")
                                st.balloons()
                                time.sleep(1)
                                st.rerun()
                        else: st.error(f"Necessário colunas 'Nome da unidade' e 'CNPJ'.")
                except Exception as e: st.error(f"Erro: {e}")

        # --- ZONA DE PERIGO (EXCLUIR TUDO) ---
        st.markdown("---")
        with st.expander("🗑️ ZONA DE PERIGO (Excluir Tudo)"):
            st.warning("Atenção: Isso apagará TODOS os documentos e tarefas.")
            confirm = st.checkbox("Sim, quero excluir tudo")
            if confirm:
                if st.button("❌ EXCLUIR TODA A LISTA", type="primary"):
                    df_prazos = pd.DataFrame(columns=["Unidade", "Setor", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido", "ID_UNICO"])
                    df_checklist = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])
                    salvar_alteracoes_completo(df_prazos, df_checklist)
                    st.session_state['doc_focado_id'] = None
                    st.success("Tudo excluído!")
                    time.sleep(1)
                    st.rerun()
        
    with col_d:
        if doc_ativo_id:
            indices = df_prazos[df_prazos['ID_UNICO'] == doc_ativo_id].index
            
            if not indices.empty:
                idx = indices[0]
                doc_nome = df_prazos.at[idx, 'Documento']
                
                # --- EDIÇÃO DO TIPO DO DOCUMENTO (LISTA DROPDOWN) ---
                c_tit, c_edit_btn = st.columns([4, 1])
                
                opcoes_docs = LISTA_TIPOS_DOCUMENTOS.copy()
                if doc_nome not in opcoes_docs:
                    opcoes_docs.insert(0, doc_nome) 
                
                try: idx_atual = opcoes_docs.index(doc_nome)
                except: idx_atual = 0

                novo_nome_doc = c_tit.selectbox("Tipo de Documento", options=opcoes_docs, index=idx_atual, key=f"nome_doc_{doc_ativo_id}")
                
                if novo_nome_doc != doc_nome:
                     if c_edit_btn.button("Salvar Tipo"):
                        antigo_id = doc_ativo_id
                        nova_unidade = df_prazos.at[idx, 'Unidade']
                        # Recria ID com CNPJ para garantir unicidade
                        cnpj_atual = df_prazos.at[idx, 'CNPJ']
                        novo_id = nova_unidade + " - " + cnpj_atual + " - " + novo_nome_doc
                        
                        df_prazos.at[idx, 'Documento'] = novo_nome_doc
                        df_prazos.at[idx, 'ID_UNICO'] = novo_id
                        df_checklist.loc[df_checklist['Documento_Ref'] == antigo_id, 'Documento_Ref'] = novo_id
                        
                        update_dados_local(df_prazos, df_checklist)
                        st.session_state['doc_focado_id'] = novo_id
                        st.rerun()

                st.caption(f"Unidade: {df_prazos.at[idx, 'Unidade']} | Setor: {df_prazos.at[idx, 'Setor']} | CNPJ: {df_prazos.at[idx, 'CNPJ']}")
                
                c_del, _ = st.columns([1, 4])
                if c_del.button("🗑️ Excluir"):
                    df_prazos = df_prazos.drop(idx).reset_index(drop=True)
                    df_checklist = df_checklist[df_checklist['Documento_Ref'] != doc_ativo_id]
                    update_dados_local(df_prazos, df_checklist)
                    st.session_state['doc_focado_id'] = None
                    st.rerun()

                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    
                    st_curr = df_prazos.at[idx, 'Status']
                    opcoes = ["NORMAL", "ALTO", "CRÍTICO"]
                    if st_curr not in opcoes: st_curr = "NORMAL"

                    novo_risco = c1.selectbox("Risco", opcoes, index=opcoes.index(st_curr), key=f"sel_r_{doc_ativo_id}")
                    if novo_risco != st_curr:
                         df_prazos.at[idx, 'Status'] = novo_risco
                         update_dados_local(df_prazos, df_checklist)
                    
                    cor_badge = "#ff4b4b" if st_curr == "CRÍTICO" else "#ffa726" if st_curr == "ALTO" else "#00c853"
                    c1.markdown(f'<span style="background-color:{cor_badge}; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; color: white;">Status: {st_curr}</span>', unsafe_allow_html=True)
                    
                    novo_setor = st.text_input("Editar Setor", value=df_prazos.at[idx, 'Setor'], key=f"edit_sector_{doc_ativo_id}")
                    if novo_setor != df_prazos.at[idx, 'Setor']:
                        df_prazos.at[idx, 'Setor'] = novo_setor
                        update_dados_local(df_prazos, df_checklist)

                    try: d_rec = pd.to_datetime(df_prazos.at[idx, 'Data_Recebimento'], dayfirst=True).date()
                    except: d_rec = date.today()
                    nova_d_rec = c2.date_input("Recebido", value=d_rec, format="DD/MM/YYYY", key=f"dt_rec_{doc_ativo_id}")
                    if nova_d_rec != d_rec:
                        df_prazos.at[idx, 'Data_Recebimento'] = nova_d_rec
                        update_dados_local(df_prazos, df_checklist)

                    try: d_venc = pd.to_datetime(df_prazos.at[idx, 'Vencimento'], dayfirst=True).date()
                    except: d_venc = date.today()
                    nova_d_venc = c3.date_input("Vence", value=d_venc, format="DD/MM/YYYY", key=f"dt_venc_{doc_ativo_id}")
                    if nova_d_venc != d_venc:
                        df_prazos.at[idx, 'Vencimento'] = nova_d_venc
                        update_dados_local(df_prazos, df_checklist)
                    
                    prog_atual = safe_prog(df_prazos.at[idx, 'Progresso'])
                    prog_bar_placeholder = st.empty()
                    prog_bar_placeholder.progress(prog_atual, text=f"Progressão: {prog_atual}%")

                st.write("✅ **Tarefas (Edição Rápida)**")
                df_checklist['Feito'] = df_checklist['Feito'].replace({'TRUE': True, 'FALSE': False, 'True': True, 'False': False, 'nan': False})
                df_checklist['Feito'] = df_checklist['Feito'].fillna(False).astype(bool)
                
                df_checklist['Documento_Ref'] = df_checklist['Documento_Ref'].astype(str)
                mask = df_checklist['Documento_Ref'] == str(doc_ativo_id)
                df_t = df_checklist[mask].copy().reset_index(drop=True)
                
                c_add, c_btn = st.columns([3, 1])
                new_t = c_add.text_input("Nova tarefa...", label_visibility="collapsed", key=f"new_t_{doc_ativo_id}")
                
                if c_btn.button("ADICIONAR", key=f"btn_add_{doc_ativo_id}"):
                    if new_t:
                        line = pd.DataFrame([{"Documento_Ref": doc_ativo_id, "Tarefa": new_t, "Feito": False}])
                        df_checklist = pd.concat([df_checklist, line], ignore_index=True)
                        update_dados_local(df_prazos, df_checklist)
                        st.rerun()

                if not df_t.empty:
                    edited = st.data_editor(
                        df_t, 
                        num_rows="dynamic", 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Documento_Ref": None,
                            "Tarefa": st.column_config.TextColumn("Descrição", width="medium"),
                            "Feito": st.column_config.CheckboxColumn("OK", width="small")
                        },
                        key=f"ed_{doc_ativo_id}"
                    )
                    
                    tot = len(edited)
                    done = edited['Feito'].sum()
                    new_p = int((done/tot)*100) if tot > 0 else 0
                    
                    prog_bar_placeholder.progress(new_p, text=f"Progressão: {new_p}%")
                    
                    if not edited.equals(df_t) or new_p != prog_atual:
                        df_prazos.at[idx, 'Progresso'] = new_p
                        
                        df_checklist = df_checklist[~mask]
                        edited['Documento_Ref'] = str(doc_ativo_id)
                        df_checklist = pd.concat([df_checklist, edited], ignore_index=True)
                        update_dados_local(df_prazos, df_checklist)
                        st.rerun()

                else: st.info("Adicione tarefas acima.")

                st.markdown("---")
                if st.button("💾 SALVAR TUDO NA NUVEM", type="primary"):
                    if salvar_alteracoes_completo(df_prazos, df_checklist): time.sleep(0.5); st.rerun()
            else:
                st.warning("Documento não encontrado.")
                if st.button("Voltar"): st.session_state['doc_focado_id'] = None; st.rerun()
        else: st.info("👈 Selecione um documento na lista.")

elif menu == "Vistoria Mobile":
    st.title("Auditoria Mobile")
    with st.container(border=True):
        c1, c2 = st.columns([1, 2])
        foto = c1.camera_input("Foto")
        setor = c2.selectbox("Local", ["Recepção", "Raio-X", "UTI", "Expurgo", "Cozinha", "Outros"])
        item = c2.text_input("Item")
        sit = c2.radio("Situação", ["❌ Irregular", "✅ Conforme"], horizontal=True)
        grav = c2.select_slider("Risco", ["Baixo", "Médio", "Alto", "CRÍTICO"])
        obs = st.text_area("Obs")
        if st.button("➕ REGISTRAR", type="primary"):
            st.session_state['vistorias'].append({"Setor": setor, "Item": item, "Situação": sit, "Gravidade": grav, "Obs": obs, "Foto_Binaria": foto})
            st.success("Registrado!")

elif menu == "Relatórios":
    st.title("Relatórios")
    tab1, tab2 = st.tabs(["Sessão Atual", "Histórico"])
    with tab1:
        if st.button("☁️ Salvar Nuvem"): salvar_vistoria_db(st.session_state['vistorias']); st.toast("Salvo!")
        if len(st.session_state['vistorias']) > 0:
            pdf = gerar_pdf(st.session_state['vistorias'])
            st.download_button("📥 Baixar PDF", data=pdf, file_name="Relatorio_Hoje.pdf", mime="application/pdf", type="primary")
    with tab2:
        try:
            sh = conectar_gsheets()
            ws = sh.worksheet("Vistorias")
            df_h = pd.DataFrame(ws.get_all_records())
            if not df_h.empty:
                sel = st.selectbox("Data:", df_h['Data'].unique())
                df_f = df_h[df_h['Data'] == sel]
                
                st.info("Edite ou exclua linhas abaixo e clique em Salvar Correções.")
                df_edited = st.data_editor(df_f, num_rows="dynamic", use_container_width=True, hide_index=True)
                
                c_save, c_down = st.columns(2)
                if c_save.button("💾 Salvar Correções no Histórico"):
                    if salvar_historico_editado(df_edited, sel): time.sleep(1); st.rerun()
                
                if c_down.button(f"📥 Baixar PDF"):
                    pdf = gerar_pdf(df_f.to_dict('records'))
                    st.download_button("Download", data=pdf, file_name=f"Relatorio_{sel}.pdf", mime="application/pdf")
        except: st.error("Sem histórico.")
