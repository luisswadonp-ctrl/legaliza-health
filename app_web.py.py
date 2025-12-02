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

# --- ⚠️ COLE O ID DA SUA PASTA DO GOOGLE DRIVE AQUI EMBAIXO ---
ID_PASTA_DRIVE = "COLOQUE_O_ID_DA_SUA_PASTA_AQUI" 
# Exemplo: "1PoX...kL9s"

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

def get_creds():
    scope = [
        "https://spreadsheets.google.com/feeds", 
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = st.secrets["gcp_service_account"]
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

def conectar_gsheets():
    creds = get_creds()
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

def upload_foto_drive(foto_binaria, nome_arquivo):
    """Sobe a foto para o Drive e retorna o Link"""
    if not ID_PASTA_DRIVE or ID_PASTA_DRIVE == "COLOQUE_O_ID_DA_SUA_PASTA_AQUI":
        st.error("ERRO: Configure o ID da pasta do Drive no código!")
        return ""
        
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': nome_arquivo,
            'parents': [ID_PASTA_DRIVE]
        }
        
        media = MediaIoBaseUpload(foto_binaria, mimetype='image/jpeg')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webContentLink').execute()
        
        # Retorna o link de download direto
        return file.get('webContentLink', '')
    except Exception as e:
        st.error(f"Erro upload Drive: {e}")
        return ""

def enviar_resumo_push(lista_problemas):
    qtd = len(lista_problemas)
    if qtd == 0: return False
    
    tem_atrasado = any("ATRASADO" in p['status'] for p in lista_problemas)
    
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
        if 'Prazo' in df_salvar.columns: df_salvar = df_salvar.drop(columns=['Prazo'])
        df_salvar['Concluido'] = df_salvar['Concluido'].astype(str)
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
        
        # Garante que o cabeçalho tenha a coluna Foto
        header = ws.row_values(1)
        if "Foto_Link" not in header:
            ws.append_row(["Setor", "Item", "Situação", "Gravidade", "Obs", "Data", "Foto_Link"])
            
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime("%d/%m/%Y")
        
        progresso = st.progress(0, text="Salvando fotos no Drive...")
        total = len(lista_itens)
        
        for i, item in enumerate(lista_itens):
            link_foto = ""
            # Se tiver foto, faz upload
            if item.get('Foto_Binaria'):
                nome_arq = f"Vistoria_{hoje.replace('/','-')}_{item['Item']}.jpg"
                link_foto = upload_foto_drive(item['Foto_Binaria'], nome_arq)
            
            ws.append_row([
                item['Setor'], item['Item'], item['Situação'], 
                item['Gravidade'], item['Obs'], hoje, link_foto
            ])
            progresso.progress((i + 1) / total)
            
        progresso.empty()
        
    except Exception as e: st.error(f"Erro salvar vistoria: {e}")

def carregar_dados_prazos():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        dados = ws.get_all_records()
        df = pd.DataFrame(dados)
        
        for col in ["Documento", "Vencimento", "Status", "Concluido"]:
            if col not in df.columns: df[col] = ""

        df['Vencimento'] = pd.to_datetime(df['Vencimento'], dayfirst=True, errors='coerce').dt.date
        df['Concluido'] = df['Concluido'].astype(str).str.upper() == 'TRUE'
        return df
    except:
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status", "Concluido"])

def carregar_historico_vistorias():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Vistorias")
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

def calcular_status_e_texto(data_venc, concluido):
    if concluido: return 999, "✅ RESOLVIDO", "---"
    if pd.isnull(data_venc): return 0, "⚪ DATA INVÁLIDA", "---"
    
    hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date()
    dias = (data_venc - hoje).days
    
    if dias < 0:
        status = "⛔ ATRASADO"
        txt = f"🚨 Atrasado há {abs(dias)} dias"
    elif dias == 0:
        status = "💥 VENCE HOJE"
        txt = "💥 Vence HOJE"
    elif dias <= 7:
        status = "🔴 CRÍTICO"
        txt = f"⏳ Vence em {dias} dias"
    elif dias <= 10:
        status = "🟠 ALTO"
        txt = f"⚠️ Vence em {dias} dias"
    else:
        status = "🟢 NORMAL"
        txt = f"📅 {dias} dias restantes"
    return dias, status, txt

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatorio LegalizaHealth', 0, 1, 'C')
        self.ln(5)
def limpar_txt(t):
    return str(t).replace("✅","").replace("❌","").encode('latin-1','replace').decode('latin-1')

def baixar_imagem_url(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return io.BytesIO(response.content)
    except: pass
    return None

def gerar_pdf(vistorias, eh_historico=False):
    pdf = PDF()
    pdf.add_page()
    
    for i, item in enumerate(vistorias):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Item #{i+1}: {limpar_txt(item['Item'])}", 0, 1)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 6, f"Local: {limpar_txt(item['Setor'])}\nObs: {limpar_txt(item.get('Obs',''))}")
        
        # LÓGICA DE FOTO HÍBRIDA
        imagem_para_pdf = None
        
        # 1. Se for vistoria de agora (tem binário na memória)
        if 'Foto_Binaria' in item and item['Foto_Binaria']:
            imagem_para_pdf = item['Foto_Binaria']
        
        # 2. Se for histórico (tem Link do Drive)
        elif 'Foto_Link' in item and item['Foto_Link'] and str(item['Foto_Link']).startswith('http'):
            imagem_para_pdf = baixar_imagem_url(item['Foto_Link'])
            
        # Inserir no PDF
        if imagem_para_pdf:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                    t.write(imagem_para_pdf.getvalue() if hasattr(imagem_para_pdf, 'getvalue') else imagem_para_pdf.read())
                    pdf.image(t.name, w=60)
            except: pass
            
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- INTERFACE ---
if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []
if 'ultima_notificacao' not in st.session_state: st.session_state['ultima_notificacao'] = datetime.min

with st.sidebar:
    if img_loading:
        st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    st.markdown("### LegalizaHealth Pro")
    menu = st.radio("Menu", ["📊 Dashboard", "📅 Gestão de Prazos", "📸 Nova Vistoria", "📂 Relatórios"])
    st.markdown("---")

# --- ROBÔ ---
try:
    agora = datetime.now()
    diff = (agora - st.session_state['ultima_notificacao']).total_seconds() / 60
    
    # Lógica Global
    df_global = carregar_dados_prazos()
    df_global['Prazo'] = ""
    criticos_lista = []
    
    for index, row in df_global.iterrows():
        d, s, t = calcular_status_e_texto(row['Vencimento'], row['Concluido'])
        df_global.at[index, 'Status'] = s
        df_global.at[index, 'Prazo'] = t
        
        if not row['Concluido']:
            if isinstance(s, str) and ("CRÍTICO" in s or "ATRASADO" in s or "HOJE" in s or "ALTO" in s):
                clean_s = s.replace("🔴 ", "").replace("⛔ ", "").replace("💥 ", "")
                criticos_lista.append({"doc": row['Documento'], "status": clean_s})

    if diff >= INTERVALO_GERAL and len(criticos_lista) > 0:
        if enviar_resumo_push(criticos_lista):
            st.session_state['ultima_notificacao'] = agora
            st.toast(f"🤖 Resumo enviado!")
except Exception as e: print(f"Erro robô: {e}")

# --- TELAS ---
if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    
    # Filtros
    is_risk = lambda row: not row['Concluido'] and ("CRÍTICO" in row['Status'] or "ATRASADO" in row['Status'] or "HOJE" in row['Status'])
    is_high = lambda row: not row['Concluido'] and "ALTO" in row['Status']
    
    df_criticos = df_global[df_global.apply(is_risk, axis=1)]
    df_atencao = df_global[df_global.apply(is_high, axis=1)]

    col1, col2, col3 = st.columns(3)
    col1.metric("🚨 Risco Imediato", len(df_criticos), delta="Ação" if len(df_criticos) > 0 else "OK", delta_color="inverse")
    col2.metric("🟠 Prioridade Alta", len(df_atencao), delta_color="off")
    col3.metric("📋 Total", len(df_global))
    st.markdown("---")
    
    if len(df_criticos) > 0:
        st.error(f"⚠️ Atenção! {len(df_criticos)} documentos requerem sua ação.")
        st.dataframe(df_criticos[['Documento', 'Vencimento', 'Prazo', 'Status']], use_container_width=True, hide_index=True)
    else:
        st.success("Tudo tranquilo.")

elif menu == "📅 Gestão de Prazos":
    st.title("Gestão de Documentos")
    st.caption("Data: DD/MM/AAAA. Coluna 'Prazo' é calculada automaticamente.")
    
    df_alterado = st.data_editor(
        df_global,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Concluido": st.column_config.CheckboxColumn("✅ Feito?", default=False),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Prazo": st.column_config.TextColumn("Prazo Estimado", disabled=True),
            "Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY", step=1),
            "Documento": st.column_config.TextColumn("Nome", width="large"),
        },
        key="editor_prazos"
    )

    if st.button("💾 SALVAR E ATUALIZAR", type="primary", use_container_width=True):
        if sincronizar_prazos_completo(df_alterado):
            st.success("Atualizado! Recarregando...")
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
    st.title("Central de Relatórios")
    
    tab1, tab2 = st.tabs(["📝 Vistoria Atual", "🗄️ Histórico Completo"])
    
    # --- TAB 1 ---
    with tab1:
        qtd = len(st.session_state['vistorias'])
        st.metric("Itens Hoje", qtd)
        if qtd > 0:
            c1, c2 = st.columns(2)
            if c1.button("☁️ Salvar Nuvem (Com Fotos)"): 
                salvar_vistoria_db(st.session_state['vistorias'])
                st.toast("Salvo no Drive e Planilha!")
            
            pdf = gerar_pdf(st.session_state['vistorias'])
            c2.download_button("📥 Baixar PDF", data=pdf, file_name="Relatorio_Hoje.pdf", mime="application/pdf", type="primary")

    # --- TAB 2 (AQUI AS FOTOS VAO APARECER SE ESTIVEREM NO DRIVE) ---
    with tab2:
        df_hist = carregar_historico_vistorias()
        if not df_hist.empty:
            datas = df_hist['Data'].unique()
            sel_data = st.selectbox("Filtrar Data:", datas)
            df_filtro = df_hist[df_hist['Data'] == sel_data]
            
            st.dataframe(df_filtro, use_container_width=True, hide_index=True)
            
            if st.button(f"📥 Re-gerar PDF de {sel_data}"):
                lista = df_filtro.to_dict('records')
                pdf_h = gerar_pdf(lista, eh_historico=True)
                st.download_button("Baixar PDF Histórico", data=pdf_h, file_name=f"Relatorio_{sel_data}.pdf", mime="application/pdf")
