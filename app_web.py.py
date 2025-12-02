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

# --- 1. CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"
INTERVALO_GERAL = 60 
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

# --- LÓGICA DE DADOS ---

def carregar_tudo():
    try:
        sh = conectar_gsheets()
        # Carrega Prazos
        ws_prazos = sh.worksheet("Prazos")
        df_prazos = pd.DataFrame(ws_prazos.get_all_records())
        
        # Carrega Checklist (Cria aba se não existir)
        try:
            ws_check = sh.worksheet("Checklist_Itens")
            df_check = pd.DataFrame(ws_check.get_all_records())
        except:
            ws_check = sh.add_worksheet("Checklist_Itens", 1000, 5)
            ws_check.append_row(["Documento_Ref", "Tarefa", "Feito"])
            df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])

        # Garante colunas
        if not df_prazos.empty:
            if "Status" not in df_prazos.columns: df_prazos["Status"] = "NORMAL"
            if "Progresso" not in df_prazos.columns: df_prazos["Progresso"] = 0
            df_prazos['Vencimento'] = pd.to_datetime(df_prazos['Vencimento'], dayfirst=True, errors='coerce').dt.date
        
        return df_prazos, df_check
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

def salvar_tudo_completo(df_prazos, df_checklist):
    try:
        sh = conectar_gsheets()
        
        # 1. Salva Prazos
        ws_prazos = sh.worksheet("Prazos")
        ws_prazos.clear()
        df_p = df_prazos.copy()
        df_p['Vencimento'] = df_p['Vencimento'].apply(lambda x: x.strftime('%d/%m/%Y') if hasattr(x, 'strftime') else str(x))
        ws_prazos.update([df_p.columns.values.tolist()] + df_p.values.tolist())
        
        # 2. Salva Checklist
        ws_check = sh.worksheet("Checklist_Itens")
        ws_check.clear()
        df_c = df_checklist.copy()
        df_c['Feito'] = df_c['Feito'].astype(str) # Converte bool para texto
        ws_check.update([df_c.columns.values.tolist()] + df_c.values.tolist())
        
        st.toast("✅ Dados Salvos e Sincronizados!", icon="☁️")
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
        prog = st.progress(0, "Salvando...")
        for i, item in enumerate(lista_itens):
            link = ""
            if item.get('Foto_Binaria'):
                nome = f"Vist_{hoje.replace('/','-')}_{item['Item']}.jpg"
                link = upload_foto_drive(item['Foto_Binaria'], nome)
            ws.append_row([item['Setor'], item['Item'], item['Situação'], item['Gravidade'], item['Obs'], hoje, link])
            prog.progress((i+1)/len(lista_itens))
        prog.empty()
    except Exception as e: st.error(f"Erro: {e}")

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatorio LegalizaHealth', 0, 1, 'C')
        self.ln(5)
def limpar_txt(t):
    return str(t).replace("✅","[OK]").replace("❌","[X]").encode('latin-1','replace').decode('latin-1')
def baixar_imagem_url(url):
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200: return io.BytesIO(resp.content)
    except: pass
    return None
def gerar_pdf(vistorias):
    pdf = PDF()
    pdf.add_page()
    for i, item in enumerate(vistorias):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Item #{i+1}: {limpar_txt(item.get('Item',''))}", 0, 1)
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

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    st.markdown("### LegalizaHealth Pro")
    st.caption("v9.3 - Checklist Integrado")
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Gestão de Documentos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")

# --- ROBÔ ---
try:
    agora = datetime.now()
    diff = (agora - st.session_state['ultima_notificacao']).total_seconds() / 60
    if diff >= INTERVALO_GERAL:
        df_p, _ = carregar_tudo()
        lista_alerta = []
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date()
        for index, row in df_p.iterrows():
            try:
                dias = (row['Vencimento'] - hoje).days
                # Alerta apenas por prazo, independente do status manual
                if dias < 0 and row['Progresso'] < 100: 
                    lista_alerta.append(f"⛔ ATRASADO: {row['Documento']}")
                elif dias <= 5 and row['Progresso'] < 100: 
                    lista_alerta.append(f"⚠️ VENCE EM {dias} DIAS: {row['Documento']}")
            except: pass
        if lista_alerta:
            msg = "\n".join(lista_alerta[:5])
            if len(lista_alerta) > 5: msg += "\n..."
            enviar_notificacao_push(f"🚨 ALERTAS DE PRAZO", msg, "high")
            st.session_state['ultima_notificacao'] = agora
            st.toast("🤖 Alertas enviados!")
except: pass

# --- TELAS ---

if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    df_p, _ = carregar_tudo()
    
    # Contagens baseadas no Status Manual do Usuário
    n_crit = len(df_p[df_p['Status'] == "CRÍTICO"])
    n_alto = len(df_p[df_p['Status'] == "ALTO"])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Risco Crítico", n_crit, delta="Manual", delta_color="inverse")
    c2.metric("🟠 Risco Alto", n_alto, delta_color="off")
    c3.metric("📋 Documentos", len(df_p))
    
    st.markdown("---")
    
    # Lista de Críticos
    if n_crit > 0:
        st.error(f"Existem {n_crit} documentos marcados como CRÍTICOS.")
        # Mostra tabela simples
        st.dataframe(df_p[df_p['Status'] == "CRÍTICO"][['Documento', 'Vencimento', 'Progresso', 'Status']], use_container_width=True, hide_index=True)
    else:
        st.success("Nenhum documento com risco crítico marcado.")

elif menu == "📅 Gestão de Documentos":
    st.title("Gestão de Documentos e Tarefas")
    
    # Carregamento com Cache de Sessão
    if 'dados_cache' not in st.session_state:
        st.session_state['dados_cache'] = carregar_tudo()
    
    df_prazos, df_checklist = st.session_state['dados_cache']
    
    # --- 1. TABELA MESTRE (DOCUMENTOS) ---
    st.info("👆 Defina o RISCO manualmente e o PRAZO. A % de conclusão sobe conforme você completa o checklist abaixo.")
    
    df_prazos_editado = st.data_editor(
        df_prazos,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Progresso": st.column_config.ProgressColumn("Conclusão", min_value=0, max_value=100, format="%d%%", disabled=True), # Bloqueado, pois é cálculo
            # AQUI ESTAVA O ERRO -> CORRIGIDO PARA SelectboxColumn
            "Status": st.column_config.SelectboxColumn("Risco Definido", options=["NORMAL", "ALTO", "CRÍTICO"], required=True),
            "Vencimento": st.column_config.DateColumn("Prazo Limite", format="DD/MM/YYYY"),
            "Documento": st.column_config.TextColumn("Nome do Documento", width="large"),
        },
        key="editor_docs"
    )
    
    st.markdown("---")
    
    # --- 2. ÁREA DE CHECKLIST (DETALHE) ---
    st.subheader("📋 Etapas do Documento")
    
    # Cria lista de documentos existentes para o seletor
    lista_docs_existentes = df_prazos_editado['Documento'].unique().tolist() if not df_prazos_editado.empty else []
    doc_selecionado = st.selectbox("Selecione qual documento você quer editar as etapas:", ["Selecione..."] + lista_docs_existentes)
    
    if doc_selecionado and doc_selecionado != "Selecione...":
        
        # Filtra as tarefas desse documento
        # Garante bool para checkbox
        df_checklist['Feito'] = df_checklist['Feito'].astype(str).str.upper() == 'TRUE'
        
        # Máscara para filtrar
        mask = df_checklist['Documento_Ref'] == doc_selecionado
        df_tarefas_doc = df_checklist[mask].copy()
        
        # Se não tiver tarefas, cria uma vazia para começar
        if df_tarefas_doc.empty:
            df_tarefas_doc = pd.DataFrame([{"Documento_Ref": doc_selecionado, "Tarefa": "Criar primeira etapa...", "Feito": False}])
        
        # Editor de Tarefas
        df_tarefas_editado = st.data_editor(
            df_tarefas_doc,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Documento_Ref": st.column_config.TextColumn("Ref", disabled=True), # Escondido/Bloqueado
                "Tarefa": st.column_config.TextColumn("Descrição da Etapa", width="large"),
                "Feito": st.column_config.CheckboxColumn("Concluído?", default=False)
            },
            key="editor_tarefas"
        )
        
        # --- LÓGICA DE CÁLCULO DE PROGRESSO ---
        # 1. Atualiza o DataFrame Mestre de Checklist com as novas tarefas
        # (Remove as velhas desse doc e põe as novas editadas)
        df_checklist = df_checklist[~mask] 
        # Garante que novas linhas tenham o nome do doc correto
        df_tarefas_editado['Documento_Ref'] = doc_selecionado
        df_checklist = pd.concat([df_checklist, df_tarefas_editado], ignore_index=True)
        
        # 2. Calcula %
        total_tasks = len(df_tarefas_editado)
        feitos = len(df_tarefas_editado[df_tarefas_editado['Feito'] == True])
        nova_pct = int((feitos / total_tasks) * 100) if total_tasks > 0 else 0
        
        # 3. Atualiza a % na Tabela Mestre de Documentos (Visualmente)
        idx_doc = df_prazos_editado[df_prazos_editado['Documento'] == doc_selecionado].index
        if not idx_doc.empty:
            df_prazos_editado.at[idx_doc[0], 'Progresso'] = nova_pct
            
        st.metric(f"Progresso de '{doc_selecionado}'", f"{nova_pct}%", delta="Calculado Automaticamente")

    # BOTÃO SALVAR GLOBAL
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 SALVAR TUDO (Docs e Etapas)", type="primary", use_container_width=True):
        if salvar_tudo_completo(df_prazos_editado, df_checklist):
            # Atualiza o cache para refletir o salvamento
            st.session_state['dados_cache'] = (df_prazos_editado, df_checklist)
            time.sleep(1)
            st.rerun()

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
                st.dataframe(df_f, use_container_width=True, hide_index=True)
                if st.button(f"📥 Baixar PDF de {sel}"):
                    pdf = gerar_pdf(df_f.to_dict('records'))
                    st.download_button("Download", data=pdf, file_name=f"Relatorio_{sel}.pdf", mime="application/pdf")
        except: st.error("Sem histórico.")
