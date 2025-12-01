import streamlit as st
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import tempfile

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LegalizaHealth", page_icon="🏥", layout="wide")

# --- FUNÇÕES ÚTEIS ---

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
    """
    Remove emojis e garante que o texto funcione no PDF padrão.
    """
    if not isinstance(texto, str):
        return str(texto)
    
    # Remove os emojis específicos
    texto = texto.replace("✅", "").replace("❌", "").replace("🔴", "").replace("🟠", "").replace("🟢", "")
    
    # Converte para latin-1 substituindo caracteres estranhos por '?'
    return texto.encode('latin-1', 'replace').decode('latin-1').strip()

def gerar_pdf(lista_vistorias):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for i, item in enumerate(lista_vistorias):
        # Limpa textos
        item_limpo = limpar_texto_para_pdf(item['Item'])
        setor_limpo = limpar_texto_para_pdf(item['Setor'])
        situacao_limpa = limpar_texto_para_pdf(item['Situação'])
        gravidade_limpa = limpar_texto_para_pdf(item['Gravidade'])
        obs_limpa = limpar_texto_para_pdf(item['Obs'])

        # Título
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"Item #{i+1}: {item_limpo} ({setor_limpo})", 0, 1)
        
        # Detalhes
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Situacao: {situacao_limpa}", 0, 1)
        pdf.cell(0, 8, f"Gravidade: {gravidade_limpa}", 0, 1)
        
        # Obs
        pdf.set_font("Arial", 'I', 11)
        pdf.multi_cell(0, 8, f"Obs: {obs_limpa}")
        pdf.ln(2)

        # Foto
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

    # --- CORREÇÃO AQUI ---
    # Retorna os bytes diretamente, sem tentar codificar de novo
    return bytes(pdf.output(dest='S'))

def calcular_status(data_vencimento):
    hoje = date.today()
    dias_restantes = (data_vencimento - hoje).days

    if dias_restantes <= 3:
        return dias_restantes, "🔴 PRIORIDADE TOTAL", "#ff4d4d"
    elif dias_restantes <= 15:
        return dias_restantes, "🟠 Atenção (Alta)", "#ffa500"
    else:
        return dias_restantes, "🟢 No Prazo", "#28a745"

# --- ESTADO E INTERFACE ---
if 'documentos' not in st.session_state:
    st.session_state['documentos'] = []
if 'vistorias' not in st.session_state:
    st.session_state['vistorias'] = []

st.sidebar.title("🏥 Menu")
menu = st.sidebar.radio("Ir para:", ["Gestão de Prazos", "Nova Vistoria", "Baixar Relatório PDF"])

if menu == "Gestão de Prazos":
    st.title("📅 Gestão de Prazos")
    col1, col2 = st.columns([2, 1])
    with col1:
        novo_doc = st.text_input("Nome do Documento")
    with col2:
        nova_data = st.date_input("Vencimento", format="DD/MM/YYYY")
    
    if st.button("➕ Adicionar Prazo"):
        if novo_doc:
            dias, status, cor = calcular_status(nova_data)
            st.session_state['documentos'].append({
                "Documento": novo_doc,
                "Vencimento": nova_data.strftime("%d/%m/%Y"),
                "Dias Restantes": dias,
                "Status": status
            })
            st.success("Adicionado!")
        else:
            st.warning("Preencha o nome.")

    if st.session_state['documentos']:
        df = pd.DataFrame(st.session_state['documentos'])
        st.dataframe(df, use_container_width=True)

elif menu == "Nova Vistoria":
    st.title("📸 Checklist de Vistoria")
    with st.form("form_vistoria", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            setor = st.selectbox("Setor", ["Recepção", "Raio-X", "UTI", "Expurgo", "Farmácia", "Cozinha", "Outro"])
            item_avaliado = st.text_input("Item Avaliado", placeholder="Ex: Extintor")
        with col_b:
            conformidade = st.radio("Situação", ["✅ Conforme", "❌ NÃO Conforme"], horizontal=True)
            prioridade = st.select_slider("Gravidade", options=["Baixa", "Média", "Alta", "CRÍTICA"])

        obs = st.text_area("Observações")
        foto = st.camera_input("Foto da Evidência")
        
        if st.form_submit_button("💾 Salvar na Lista"):
            st.session_state['vistorias'].append({
                "Setor": setor,
                "Item": item_avaliado,
                "Situação": conformidade,
                "Gravidade": prioridade,
                "Obs": obs,
                "Foto_Binaria": foto 
            })
            st.success("Salvo! Vá para Relatórios.")

elif menu == "Baixar Relatório PDF":
    st.title("📄 Exportar Relatório")
    qtd = len(st.session_state['vistorias'])
    st.write(f"Itens vistoriados: **{qtd}**")
    
    if qtd > 0:
        for item in st.session_state['vistorias']:
            with st.expander(f"{item['Item']} - {item['Setor']}"):
                st.write(item['Situação'])
                if item['Foto_Binaria']: st.image(item['Foto_Binaria'], width=200)

        if st.button("Gerar PDF Agora"):
            try:
                pdf_bytes = gerar_pdf(st.session_state['vistorias'])
                st.download_button(
                    label="📥 Baixar PDF Final",
                    data=pdf_bytes,
                    file_name=f"relatorio_{date.today()}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Erro: {e}")
    else:
        st.info("Nenhuma vistoria feita ainda.")
