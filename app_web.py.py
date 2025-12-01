import streamlit as st
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURAÇÃO VISUAL E CSS (DESIGN) ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# CSS Customizado para dar um visual "App Nativo"
st.markdown("""
<style>
    /* Fundo dos cartões de métricas */
    div[data-testid="metric-container"] {
        background-color: #f0f2f6;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
        color: #31333F;
    }
    /* Botões arredondados e modernos */
    .stButton>button {
        border-radius: 20px;
        font-weight: bold;
        border: none;
        transition: 0.3s;
    }
    /* Destaque para o botão de salvar */
    div[data-testid="stButton"] > button:hover {
        transform: scale(1.02);
    }
</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO COM GOOGLE SHEETS ---
def conectar_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

# --- 3. LÓGICA DE NEGÓCIO ---

def sincronizar_prazos_completo(df_novo):
    """
    Apaga a planilha de Prazos antiga e reescreve com a tabela editada na tela.
    Isso permite editar e excluir itens facilmente.
    """
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        ws.clear() # Limpa tudo
        # Prepara os dados: Adiciona cabeçalho e converte para lista
        lista_dados = [df_novo.columns.values.tolist()] + df_novo.values.tolist()
        ws.update(lista_dados)
        st.toast("✅ Nuvem sincronizada com sucesso!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro ao sincronizar: {e}")
        return False

def salvar_vistoria_db(lista_itens):
    try:
        sh = conectar_gsheets()
        try:
            ws = sh.worksheet("Vistorias")
        except:
            ws = sh.add_worksheet(title="Vistorias", rows=1000, cols=10)
            ws.append_row(["Setor", "Item", "Situação", "Gravidade", "Obs", "Data"])

        hoje = date.today().strftime("%d/%m/%Y")
        for item in lista_itens:
            ws.append_row([
                item['Setor'], item['Item'], item['Situação'], 
                item['Gravidade'], item['Obs'], hoje
            ])
    except Exception as e:
        st.error(f"Erro ao salvar vistoria: {e}")

def carregar_dados_prazos():
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        dados = ws.get_all_records()
        return pd.DataFrame(dados)
    except:
        return pd.DataFrame(columns=["Documento", "Vencimento", "Status"])

def calcular_status_e_cor(data_vencimento_str):
    try:
        if isinstance(data_vencimento_str, date):
            data_venc = data_vencimento_str
        else:
            data_venc = datetime.strptime(data_vencimento_str, "%d/%m/%Y").date()
            
        hoje = date.today()
        dias = (data_venc - hoje).days

        if dias <= 3: return dias, "🔴 CRÍTICO"
        elif dias <= 15: return dias, "🟠 ALTA"
        else: return dias, "🟢 NORMAL"
    except:
        return 0, "⚪ ERRO"

# --- PDF GENERATOR (Mantido e Compactado) ---
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
    pdf.set_font("Arial", size=12)
    for i, item in enumerate(vistorias):
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"#{i+1}: {limpar_txt(item['Item'])} ({limpar_txt(item['Setor'])})", 0, 1)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Status: {limpar_txt(item['Situação'])} | Gravidade: {limpar_txt(item['Gravidade'])}", 0, 1)
        pdf.multi_cell(0, 8, f"Obs: {limpar_txt(item['Obs'])}")
        if item['Foto_Binaria']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                t.write(item['Foto_Binaria'].getbuffer())
                pdf.image(t.name, w=70)
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- 4. INTERFACE PRINCIPAL (UI) ---

# Sidebar mais limpa
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=80)
    st.title("LegalizaHealth")
    st.markdown("Sistema de Gestão Hospitalar")
    st.markdown("---")
    menu = st.radio("Navegação", ["📊 Dashboard", "📅 Gestão de Prazos", "📸 Vistoria", "📂 Relatórios"])
    st.info("Versão Cloud 2.0")

# Inicialização de Estado
if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []

# --- TELA 1: DASHBOARD (NOVO!) ---
if menu == "📊 Dashboard":
    st.title("Painel de Controle")
    st.markdown("Visão geral da conformidade do hospital.")
    
    # Carrega dados para mostrar números reais
    df = carregar_dados_prazos()
    
    # Calcula métricas
    total_docs = len(df)
    
    # Recalcula status em tempo real para o dashboard
    criticos = 0
    atencao = 0
    for data_str in df['Vencimento']:
        d, s = calcular_status_e_cor(data_str)
        if "CRÍTICO" in s: criticos += 1
        if "ALTA" in s: atencao += 1

    # Colunas de métricas bonitas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documentos Monitorados", total_docs, border=True)
    col2.metric("Prioridade Extrema", criticos, delta="-Urgentíssimo" if criticos > 0 else "Ok", delta_color="inverse", border=True)
    col3.metric("Atenção Necessária", atencao, delta_color="off", border=True)
    col4.metric("Vistorias na Sessão", len(st.session_state['vistorias']), border=True)

    st.markdown("---")
    st.subheader("⚠️ Itens de Maior Risco")
    if criticos > 0:
        st.error(f"Existem {criticos} documentos vencendo em menos de 3 dias!")
    else:
        st.success("Nenhuma prioridade crítica no momento.")

# --- TELA 2: GESTÃO DE PRAZOS (MODERNIZADA) ---
elif menu == "📅 Gestão de Prazos":
    st.title("Central de Documentos")
    st.markdown("Edite datas, nomes ou adicione novos itens diretamente na tabela abaixo.")

    # Carrega dados do Google Sheets
    if 'df_prazos' not in st.session_state:
        st.session_state['df_prazos'] = carregar_dados_prazos()

    df_editavel = st.session_state['df_prazos']

    # --- O PULO DO GATO: Tabela Editável ---
    # num_rows="dynamic" permite adicionar e deletar linhas clicando na tabela!
    df_alterado = st.data_editor(
        df_editavel,
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "Status": st.column_config.TextColumn("Status (Calculado)", disabled=True), # Bloqueia edição do status (é automático)
            "Vencimento": st.column_config.TextColumn("Vencimento (DD/MM/AAAA)"),
            "Documento": st.column_config.TextColumn("Nome do Documento", width="large"),
        },
        key="editor_prazos"
    )

    # Botão para efetivar as mudanças
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("💾 Salvar Alterações na Nuvem", type="primary"):
            # Recalcula status antes de salvar
            for index, row in df_alterado.iterrows():
                try:
                    d, s = calcular_status_e_cor(row['Vencimento'])
                    df_alterado.at[index, 'Status'] = s
                except:
                    pass
            
            # Manda pro Google Sheets
            sucesso = sincronizar_prazos_completo(df_alterado)
            if sucesso:
                st.session_state['df_prazos'] = df_alterado # Atualiza memória local
                st.balloons() # Efeito visual de sucesso
    
    with col_btn2:
        st.caption("ℹ️ Para **Excluir**: Selecione a linha e aperte Delete no teclado. Para **Adicionar**: Clique na linha vazia no final.")

# --- TELA 3: VISTORIA (MANTIDA MAS BONITA) ---
elif menu == "📸 Vistoria":
    st.title("Checklist Mobile")
    
    with st.container(border=True): # Caixa em volta para organizar
        col_cam, col_form = st.columns([1, 1.5])
        
        with col_cam:
            st.write("**1. Evidência**")
            foto = st.camera_input("Tirar Foto")
        
        with col_form:
            st.write("**2. Detalhes**")
            setor = st.selectbox("Local", ["Recepção", "Raio-X", "UTI", "Expurgo", "Cozinha", "Outros"])
            item = st.text_input("Item Avaliado")
            
            c1, c2 = st.columns(2)
            sit = c1.radio("Situação", ["✅ Conforme", "❌ Irregular"])
            grav = c2.select_slider("Gravidade", ["Baixa", "Média", "Alta", "CRÍTICA"])
            
            obs = st.text_area("Observações")
            
            if st.button("➕ Registrar Item", use_container_width=True):
                st.session_state['vistorias'].append({
                    "Setor": setor, "Item": item, "Situação": sit,
                    "Gravidade": grav, "Obs": obs, "Foto_Binaria": foto
                })
                st.success("Registrado!")

# --- TELA 4: RELATÓRIOS ---
elif menu == "📂 Relatórios":
    st.title("Exportação")
    
    qtd = len(st.session_state['vistorias'])
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"Itens nesta sessão: **{qtd}**")
    with col2:
        if st.button("☁️ Salvar Histórico no Drive"):
            if qtd > 0:
                salvar_vistoria_db(st.session_state['vistorias'])
                st.toast("Histórico salvo!")
            else:
                st.warning("Lista vazia.")

    st.markdown("### Prévia")
    for item in st.session_state['vistorias']:
        with st.expander(f"{item['Situação']} - {item['Item']}"):
            st.write(item['Obs'])
            if item['Foto_Binaria']: st.image(item['Foto_Binaria'], width=150)
            
    if qtd > 0:
        pdf_bytes = gerar_pdf(st.session_state['vistorias'])
        st.download_button("📥 Baixar Relatório PDF Completo", data=pdf_bytes, file_name="relatorio.pdf", mime="application/pdf", type="primary")
