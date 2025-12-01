import streamlit as st
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LegalizaHealth", page_icon="🏥", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_gsheets():
    # Define o escopo (permissões)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Pega as credenciais do cofre do Streamlit (Secrets)
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    # Abre a planilha pelo nome
    return client.open("LegalizaHealth_DB")

# --- FUNÇÕES DE BANCO DE DADOS ---
def carregar_dados():
    try:
        sh = conectar_gsheets()
        # Carrega Prazos
        worksheet_prazos = sh.worksheet("Prazos")
        dados_prazos = worksheet_prazos.get_all_records()
        
        # Carrega Vistorias (opcional, se quiser histórico)
        # worksheet_vistorias = sh.worksheet("Vistorias")
        
        return dados_prazos
    except Exception as e:
        st.error(f"Erro ao conectar na planilha: {e}")
        return []

def salvar_prazo_db(documento, vencimento, status):
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Prazos")
        # Adiciona nova linha
        ws.append_row([documento, vencimento, status])
        st.toast("Salvo no Google Sheets!")
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

def salvar_vistoria_db(lista_itens):
    """Salva o resumo da vistoria na planilha"""
    try:
        sh = conectar_gsheets()
        ws = sh.worksheet("Vistorias")
        hoje = date.today().strftime("%d/%m/%Y")
        
        for item in lista_itens:
            # Formato: Setor, Item, Situação, Gravidade, Obs, Data
            ws.append_row([
                item['Setor'], 
                item['Item'], 
                item['Situação'], 
                item['Gravidade'], 
                item['Obs'],
                hoje
            ])
    except Exception as e:
        st.error(f"Erro ao salvar vistoria na nuvem: {e}")

# --- FUNÇÕES DE PDF (Mantidas) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatorio de Vistoria - LegalizaHealth', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def limpar_texto_para_pdf(texto):
    if not isinstance(texto, str): return str(texto)
    texto = texto.replace("✅", "").replace("❌", "").replace("🔴", "").replace("🟠", "").replace("🟢", "")
    return texto.encode('latin-1', 'replace').decode('latin-1').strip()

def gerar_pdf(lista_vistorias):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for i, item in enumerate(lista_vistorias):
        item_limpo = limpar_texto_para_pdf(item['Item'])
        setor_limpo = limpar_texto_para_pdf(item['Setor'])
        situacao_limpa = limpar_texto_para_pdf(item['Situação'])
        gravidade_limpa = limpar_texto_para_pdf(item['Gravidade'])
        obs_limpa = limpar_texto_para_pdf(item['Obs'])

        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"Item #{i+1}: {item_limpo} ({setor_limpo})", 0, 1)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Situacao: {situacao_limpa}", 0, 1)
        pdf.cell(0, 8, f"Gravidade: {gravidade_limpa}", 0, 1)
        pdf.set_font("Arial", 'I', 11)
        pdf.multi_cell(0, 8, f"Obs: {obs_limpa}")
        pdf.ln(2)

        if item['Foto_Binaria'] is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                temp_img.write(item['Foto_Binaria'].getbuffer())
                temp_path = temp_img.name
            try:
                pdf.image(temp_path, w=80)
                pdf.ln(5)
            except:
                pdf.cell(0, 10, "[Erro Imagem]", 0, 1)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)
    return bytes(pdf.output(dest='S'))

def calcular_status(data_vencimento):
    hoje = date.today()
    dias_restantes = (data_vencimento - hoje).days
    if dias_restantes <= 3: return dias_restantes, "🔴 PRIORIDADE TOTAL", "#ff4d4d"
    elif dias_restantes <= 15: return dias_restantes, "🟠 Atenção (Alta)", "#ffa500"
    else: return dias_restantes, "🟢 No Prazo", "#28a745"

# --- INICIALIZAÇÃO (Carrega dados ao abrir) ---
if 'dados_carregados' not in st.session_state:
    st.session_state['documentos'] = carregar_dados() # Busca no Google Sheets
    st.session_state['dados_carregados'] = True

if 'vistorias' not in st.session_state:
    st.session_state['vistorias'] = []

# --- INTERFACE ---
st.sidebar.title("🏥 Menu")
menu = st.sidebar.radio("Ir para:", ["Gestão de Prazos", "Nova Vistoria", "Baixar Relatório PDF"])

if menu == "Gestão de Prazos":
    st.title("📅 Gestão de Prazos (Conectado ao Drive)")
    
    col1, col2 = st.columns([2, 1])
    with col1: novo_doc = st.text_input("Nome do Documento")
    with col2: nova_data = st.date_input("Vencimento", format="DD/MM/YYYY")
    
    if st.button("➕ Adicionar e Salvar"):
        if novo_doc:
            dias, status, cor = calcular_status(nova_data)
            # 1. Salva na Memória do App (Visual)
            st.session_state['documentos'].append({
                "Documento": novo_doc,
                "Vencimento": nova_data.strftime("%d/%m/%Y"),
                "Status": status
            })
            # 2. Salva no Google Sheets (Eterno)
            salvar_prazo_db(novo_doc, nova_data.strftime("%d/%m/%Y"), status)
            st.success("Adicionado e Salvo na Nuvem!")
            st.rerun() # Atualiza a tabela

    if st.session_state['documentos']:
        df = pd.DataFrame(st.session_state['documentos'])
        st.dataframe(df, use_container_width=True)

elif menu == "Nova Vistoria":
    st.title("📸 Checklist")
    with st.form("form_vistoria", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            setor = st.selectbox("Setor", ["Recepção", "Raio-X", "UTI", "Expurgo", "Farmácia", "Cozinha"])
            item_avaliado = st.text_input("Item")
        with col_b:
            conformidade = st.radio("Situação", ["✅ Conforme", "❌ NÃO Conforme"], horizontal=True)
            prioridade = st.select_slider("Gravidade", options=["Baixa", "Média", "Alta", "CRÍTICA"])
        obs = st.text_area("Obs")
        foto = st.camera_input("Foto")
        
        if st.form_submit_button("💾 Salvar Item"):
            st.session_state['vistorias'].append({
                "Setor": setor, "Item": item_avaliado, "Situação": conformidade,
                "Gravidade": prioridade, "Obs": obs, "Foto_Binaria": foto 
            })
            st.success("Item salvo temporariamente.")

elif menu == "Baixar Relatório PDF":
    st.title("📄 Finalizar Relatório")
    qtd = len(st.session_state['vistorias'])
    st.write(f"Itens: {qtd}")
    
    if qtd > 0:
        if st.button("🚀 Gerar PDF e Salvar Histórico"):
            # 1. Salva histórico na Planilha Vistorias
            salvar_vistoria_db(st.session_state['vistorias'])
            st.toast("Histórico salvo no Google Sheets!")
            
            # 2. Gera PDF
            try:
                pdf_bytes = gerar_pdf(st.session_state['vistorias'])
                st.download_button("📥 Baixar PDF", data=pdf_bytes, file_name=f"relatorio_{date.today()}.pdf", mime="application/pdf")
            except Exception as e: st.error(f"Erro PDF: {e}")
