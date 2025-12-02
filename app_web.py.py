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

# --- FUNÇÕES VISUAIS ---
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f: data = f.read()
        return base64.b64encode(data).decode()
    except: return ""

img_loading = get_img_as_base64("loading.gif")

# Função de Progresso Segura
def safe_prog(val):
    try: return max(0, min(100, int(float(val))))
    except: return 0

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    
    /* Remove padding excessivo do topo */
    .block-container { padding-top: 1rem; padding-bottom: 5rem; }
    
    /* Cards de Métricas */
    div[data-testid="metric-container"] {
        background-color: #1f2937; border: 1px solid #374151;
        padding: 15px; border-radius: 10px;
    }
    
    /* Botões */
    .stButton>button {
        border-radius: 8px; font-weight: bold; text-transform: uppercase;
        background-image: linear-gradient(to right, #2563eb, #1d4ed8);
        border: none; color: white;
    }
    
    /* Barra de Progresso Verde */
    .stProgress > div > div > div > div { background-color: #00c853; }
    
    /* Estilo dos Filtros */
    .stMultiSelect, .stTextInput { margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO E DADOS ---

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

def carregar_tudo():
    try:
        sh = conectar_gsheets()
        
        # --- CARREGA PRAZOS ---
        try:
            ws_prazos = sh.worksheet("Prazos")
            df_prazos = pd.DataFrame(ws_prazos.get_all_records())
        except:
            ws_prazos = sh.add_worksheet("Prazos", 1000, 10)
            df_prazos = pd.DataFrame()

        # --- CARREGA CHECKLIST ---
        try:
            ws_check = sh.worksheet("Checklist_Itens")
            df_check = pd.DataFrame(ws_check.get_all_records())
        except:
            ws_check = sh.add_worksheet("Checklist_Itens", 1000, 5)
            ws_check.append_row(["Documento_Ref", "Tarefa", "Feito"])
            df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])

        # --- VACINA CONTRA ERROS DE COLUNA ---
        # Adicionamos as colunas novas que você pediu
        colunas_obrigatorias = ["Unidade", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido"]
        
        for col in colunas_obrigatorias:
            if col not in df_prazos.columns:
                df_prazos[col] = "" 
        
        # Tratamento de Tipos
        if not df_prazos.empty:
            df_prazos["Progresso"] = pd.to_numeric(df_prazos["Progresso"], errors='coerce').fillna(0).astype(int)
            
            # Tratamento de Datas (Tenta BR, se falhar tenta ISO)
            for col_data in ['Vencimento', 'Data_Recebimento']:
                df_prazos[col_data] = pd.to_datetime(df_prazos[col_data], dayfirst=True, errors='coerce').dt.date
            
            # Limpa linhas vazias
            df_prazos = df_prazos[df_prazos['Documento'] != ""]
        
        if df_check.empty:
             df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])
        else:
             df_check = df_check[df_check['Tarefa'] != ""]
        
        return df_prazos, df_check
    except Exception as e:
        # st.error(f"Erro ao carregar: {e}") 
        return pd.DataFrame(columns=["Documento"]), pd.DataFrame(columns=["Documento_Ref"])

def salvar_alteracoes_completo(df_prazos, df_checklist):
    try:
        sh = conectar_gsheets()
        
        ws_prazos = sh.worksheet("Prazos")
        ws_prazos.clear()
        df_p = df_prazos.copy()
        
        # Formata datas para string antes de salvar
        for col_data in ['Vencimento', 'Data_Recebimento']:
            df_p[col_data] = df_p[col_data].apply(lambda x: x.strftime('%d/%m/%Y') if hasattr(x, 'strftime') else str(x))
            
        df_p['Concluido'] = df_p['Concluido'].astype(str)
        df_p['Progresso'] = df_p['Progresso'].apply(safe_prog)
        
        ws_prazos.update([df_p.columns.values.tolist()] + df_p.values.tolist())
        
        ws_check = sh.worksheet("Checklist_Itens")
        ws_check.clear()
        df_c = df_checklist.copy()
        df_c['Feito'] = df_c['Feito'].astype(str)
        ws_check.update([df_c.columns.values.tolist()] + df_c.values.tolist())
        
        st.toast("✅ Nuvem Sincronizada!", icon="☁️")
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
            link = ""
            if item.get('Foto_Binaria'):
                nome = f"Vist_{hoje.replace('/','-')}_{item['Item']}.jpg"
                link = upload_foto_drive(item['Foto_Binaria'], nome)
            ws.append_row([item['Setor'], item['Item'], item['Situação'], item['Gravidade'], item['Obs'], hoje, link])
            progresso.progress((i + 1) / len(lista_itens))
        progresso.empty()
    except Exception as e: st.error(f"Erro vistoria: {e}")

def carregar_historico_vistorias():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Vistorias")
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatorio LegalizaHealth', 0, 1, 'C')
        self.ln(5)

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
# Memória persistente do documento aberto
if 'doc_focado' not in st.session_state: st.session_state['doc_focado'] = None

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    st.markdown("### LegalizaHealth Pro")
    st.caption("v14.0 - Filters & New Data")
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Gestão de Documentos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")

# --- ROBÔ ---
try:
    agora = datetime.now()
    diff = (agora - st.session_state['ultima_notificacao']).total_seconds() / 60
    
    # Tenta usar cache local se existir (mais atualizado)
    df_alertas = st.session_state.get('dados_cache', [None])[0]
    if df_alertas is None and diff >= INTERVALO_GERAL:
        df_alertas, _ = carregar_tudo()
        
    if df_alertas is not None and diff >= INTERVALO_GERAL:
        lista_alerta = []
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date()
        for index, row in df_alertas.iterrows():
            try:
                dias = (row['Vencimento'] - hoje).days
                prog = safe_prog(row['Progresso'])
                if dias < 0 and prog < 100: lista_alerta.append(f"⛔ ATRASADO: {row['Documento']} ({row['Unidade']})")
                elif dias <= 5 and prog < 100: lista_alerta.append(f"⚠️ VENCE EM {dias} DIAS: {row['Documento']}")
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
    if 'dados_cache' in st.session_state: df_p = st.session_state['dados_cache'][0]
    else: df_p, _ = carregar_tudo()
    
    n_crit = len(df_p[df_p['Status'] == "CRÍTICO"])
    n_alto = len(df_p[df_p['Status'] == "ALTO"])
    c1, c2, c3 = st.columns(3)
    c1.metric("🔴 Críticos", n_crit, delta="Definido", delta_color="inverse")
    c2.metric("🟠 Alto Risco", n_alto, delta_color="off")
    c3.metric("📋 Total de Processos", len(df_p))
    
    st.markdown("---")
    
    if n_crit > 0:
        st.error(f"⚠️ {n_crit} Documentos CRÍTICOS.")
        # Mostra também a unidade no Dashboard
        st.dataframe(df_p[df_p['Status'] == "CRÍTICO"][['Unidade', 'Documento', 'Vencimento', 'Progresso']], use_container_width=True, hide_index=True)
    else: st.success("Tudo sob controle.")

elif menu == "📅 Gestão de Documentos":
    st.title("Gestão de Documentos")
    
    if 'dados_cache' not in st.session_state:
        st.session_state['dados_cache'] = carregar_tudo()
    df_prazos, df_checklist = st.session_state['dados_cache']
    
    # --- ÁREA DE FILTROS SUPERIOR ---
    with st.expander("🔍 FILTROS & BUSCA (Clique para expandir)", expanded=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        
        # Filtro de Unidade (Pega valores únicos da coluna Unidade)
        lista_unidades = ["Todas"] + sorted(list(df_prazos['Unidade'].unique())) if 'Unidade' in df_prazos.columns else ["Todas"]
        filtro_unidade = col_f1.selectbox("Unidade:", lista_unidades)
        
        filtro_status = col_f2.multiselect("Status:", ["CRÍTICO", "ALTO", "NORMAL"], default=[])
        
        busca_texto = col_f3.text_input("Buscar (Nome/CNPJ/Doc):")
        
        # Botão Limpar
        if col_f4.button("Limpar Filtros"):
            st.rerun()

    # APLICA FILTROS
    df_filtrado = df_prazos.copy()
    if filtro_unidade != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Unidade'] == filtro_unidade]
    if filtro_status:
        df_filtrado = df_filtrado[df_filtrado['Status'].isin(filtro_status)]
    if busca_texto:
        # Busca em várias colunas
        df_filtrado = df_filtrado[
            df_filtrado['Documento'].str.contains(busca_texto, case=False, na=False) | 
            df_filtrado['Unidade'].str.contains(busca_texto, case=False, na=False) |
            df_filtrado['CNPJ'].str.contains(busca_texto, case=False, na=False)
        ]

    # --- LAYOUT PRINCIPAL ---
    col_lista, col_detalhe = st.columns([1.2, 2])
    
    with col_lista:
        st.info(f"Mostrando {len(df_filtrado)} documentos.")
        
        # TABELA DE SELEÇÃO FILTRADA
        # Mostra Unidade e Nome para facilitar identificação
        selection = st.dataframe(
            df_filtrado[['Unidade', 'Documento', 'Status']], 
            use_container_width=True, 
            hide_index=True, 
            selection_mode="single-row", 
            on_select="rerun",
            column_config={
                "Status": st.column_config.TextColumn("Risco", width="small"),
                "Unidade": st.column_config.TextColumn("Unidade", width="medium")
            }
        )
        
        if len(selection.selection.rows) > 0:
            idx_selecionado = selection.selection.rows[0]
            # Pega o ID real do documento baseado no dataframe FILTRADO
            doc_selecionado = df_filtrado.iloc[idx_selecionado]['Documento']
            st.session_state['doc_focado'] = doc_selecionado
        
        # Recupera memória
        doc_ativo = st.session_state.get('doc_focado')
        
        st.markdown("---")
        with st.expander("➕ Cadastrar Novo"):
            with st.form("form_novo", clear_on_submit=True):
                n_unidade = st.text_input("Unidade (Loja/Hospital)")
                n_doc = st.text_input("Nome do Documento")
                n_cnpj = st.text_input("CNPJ")
                if st.form_submit_button("Criar"):
                    if n_doc:
                        novo = {
                            "Unidade": n_unidade, "Documento": n_doc, "CNPJ": n_cnpj,
                            "Data_Recebimento": date.today(), "Vencimento": date.today(),
                            "Status": "NORMAL", "Progresso": 0, "Concluido": "False"
                        }
                        df_prazos = pd.concat([pd.DataFrame([novo]), df_prazos], ignore_index=True)
                        salvar_alteracoes_completo(df_prazos, df_checklist)
                        st.session_state['dados_cache'] = (df_prazos, df_checklist)
                        st.rerun()

    with col_detalhe:
        if doc_ativo:
            # Busca linha original no DF completo
            indices = df_prazos[df_prazos['Documento'] == doc_ativo].index
            if not indices.empty:
                idx = indices[0]
                st.subheader(f"📝 {doc_ativo}")
                st.caption(f"Unidade: {df_prazos.at[idx, 'Unidade']} | CNPJ: {df_prazos.at[idx, 'CNPJ']}")
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    
                    # Coluna 1: Risco e Status
                    curr_status = df_prazos.at[idx, 'Status']
                    if curr_status not in ["NORMAL", "ALTO", "CRÍTICO"]: curr_status = "NORMAL"
                    novo_risco = c1.selectbox("Risco", ["NORMAL", "ALTO", "CRÍTICO"], index=["NORMAL", "ALTO", "CRÍTICO"].index(curr_status), key="sel_r")
                    
                    # Coluna 2: Datas
                    dt_rec = df_prazos.at[idx, 'Data_Recebimento']
                    if pd.isnull(dt_rec): dt_rec = date.today()
                    nova_dt_rec = c2.date_input("Recebido em", value=dt_rec, format="DD/MM/YYYY", key="dt_rec")
                    
                    dt_venc = df_prazos.at[idx, 'Vencimento']
                    if pd.isnull(dt_venc): dt_venc = date.today()
                    nova_dt_venc = c3.date_input("Vence em", value=dt_venc, format="DD/MM/YYYY", key="dt_venc")
                    
                    # Atualiza Memória
                    df_prazos.at[idx, 'Status'] = novo_risco
                    df_prazos.at[idx, 'Data_Recebimento'] = nova_dt_rec
                    df_prazos.at[idx, 'Vencimento'] = nova_dt_venc
                    st.session_state['dados_cache'] = (df_prazos, df_checklist)
                    
                    # Progresso Visual
                    prog_atual = safe_prog(df_prazos.at[idx, 'Progresso'])
                    st.progress(prog_atual, text=f"Conclusão: {prog_atual}%")

                # Checklist
                st.write("✅ **Etapas e Tarefas**")
                df_checklist['Feito'] = df_checklist['Feito'].astype(str).str.upper() == 'TRUE'
                mask = df_checklist['Documento_Ref'] == doc_ativo
                df_tarefas = df_checklist[mask].copy()
                
                # Add Tarefa
                col_add_txt, col_add_btn = st.columns([3, 1])
                new_task = col_add_txt.text_input("Nova tarefa...", label_visibility="collapsed")
                if col_add_btn.button("Adicionar", use_container_width=True):
                    if new_task:
                        line = pd.DataFrame([{"Documento_Ref": doc_ativo, "Tarefa": new_task, "Feito": False}])
                        df_checklist = pd.concat([df_checklist, line], ignore_index=True)
                        st.session_state['dados_cache'] = (df_prazos, df_checklist)
                        st.rerun()

                if not df_tarefas.empty:
                    edited = st.data_editor(
                        df_tarefas, 
                        num_rows="fixed", 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Documento_Ref": None,
                            "Tarefa": st.column_config.TextColumn("Descrição", width="large", disabled=True),
                            "Feito": st.column_config.CheckboxColumn("OK", width="small")
                        },
                        key=f"editor_{doc_ativo}"
                    )
                    
                    # Cálculo Progresso
                    total = len(edited)
                    feitos = edited['Feito'].sum()
                    novo_p = int((feitos/total)*100) if total > 0 else 0
                    
                    if novo_p != prog_atual:
                        df_prazos.at[idx, 'Progresso'] = novo_p
                        st.session_state['dados_cache'] = (df_prazos, df_checklist) # Salva
                        
                    # Reconstrói checklist mestre
                    df_checklist = df_checklist[~mask]
                    edited['Documento_Ref'] = doc_ativo
                    df_checklist = pd.concat([df_checklist, edited], ignore_index=True)
                    
                    # Persistência de Estado do Checklist
                    st.session_state['dados_cache'] = (df_prazos, df_checklist)
                    
                    if novo_p != prog_atual: st.rerun()

                else: st.info("Adicione tarefas acima.")

                st.markdown("---")
                if st.button("💾 SALVAR TUDO NA NUVEM", type="primary", use_container_width=True):
                    if salvar_alteracoes_completo(df_prazos, df_checklist):
                        time.sleep(0.5); st.rerun()
            else:
                st.warning("Documento não encontrado. Se você acabou de filtrar, limpe o filtro.")
        else: st.info("👈 Selecione um documento na lista.")

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
