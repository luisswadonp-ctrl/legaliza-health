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
        self.cell(0, 10, 'Relatório de Vistoria - LegalizaHealth', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def gerar_pdf(lista_vistorias):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    for i, item in enumerate(lista_vistorias):
        # Título do Item
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"Item #{i+1}: {item['Item']} ({item['Setor']})", 0, 1)
        
        # Detalhes
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 8, f"Situação: {item['Situação']}", 0, 1)
        pdf.cell(0, 8, f"Gravidade: {item['Gravidade']}", 0, 1)
        
        # Observação (Multi-cell para quebra de linha automática)
        pdf.set_font("Arial", 'I', 11)
        pdf.multi_cell(0, 8, f"Obs: {item['Obs']}")
        pdf.ln(2)

        # Foto
        if item['Foto_Binaria'] is not None:
            # Salva a imagem temporariamente para o PDF ler
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                temp_img.write(item['Foto_Binaria'].getbuffer())
                temp_path = temp_img.name
            
            # Adiciona ao PDF (Largura 60mm)
            try:
                pdf.image(temp_path, w=80)
                pdf.ln(5)
            except:
                pdf.cell(0, 10, "[Erro ao processar imagem]", 0, 1)
        
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()) # Linha divisória
        pdf.ln(10)

    # Retorna o binário do PDF
    return pdf.output(dest='S').encode('latin-1')

def calcular_status(data_vencimento):
    # Recebe objeto DATE, não string. Mais fácil!
    hoje = date.today()
    dias_restantes = (data_vencimento - hoje).days

    if dias_restantes <= 3:
        return dias_restantes, "🔴 PRIORIDADE TOTAL", "#ff4d4d"
    elif dias_restantes <= 15:
        return dias_restantes, "🟠 Atenção (Alta)", "#ffa500"
    else:
        return dias_restantes, "🟢 No Prazo", "#28a745"

# --- ESTADO DA SESSÃO ---
if 'documentos' not in st.session_state:
    st.session_state['documentos'] = []
if 'vistorias' not in st.session_state:
    st.session_state['vistorias'] = []

# --- INTERFACE ---
st.sidebar.title("🏥 Menu")
menu = st.sidebar.radio("Ir para:", ["Gestão de Prazos", "Nova Vistoria", "Baixar Relatório PDF"])

# --- 1. GESTÃO DE PRAZOS ---
if menu == "Gestão de Prazos":
    st.title("📅 Gestão de Prazos")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        novo_doc = st.text_input("Nome do Documento")
    with col2:
        # AQUI ESTÁ A CORREÇÃO DA DATA:
        nova_data = st.date_input("Vencimento", format="DD/MM/YYYY")
    
    if st.button("➕ Adicionar Prazo"):
        if novo_doc:
            dias, status, cor = calcular_status(nova_data)
            st.session_state['documentos'].append({
                "Documento": novo_doc,
                "Vencimento": nova_data.strftime("%d/%m/%Y"), # Formata bonito para tabela
                "Dias Restantes": dias,
                "Status": status
            })
            st.success("Adicionado!")
        else:
            st.warning("Digite o nome do documento.")

    if st.session_state['documentos']:
        df = pd.DataFrame(st.session_state['documentos'])
        st.dataframe(df, use_container_width=True)

# --- 2. NOVA VISTORIA ---
elif menu == "Nova Vistoria":
    st.title("📸 Checklist de Vistoria")
    
    with st.form("form_vistoria", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            setor = st.selectbox("Setor", ["Recepção", "Raio-X", "UTI", "Expurgo", "Farmácia", "Cozinha", "Outro"])
            item_avaliado = st.text_input("Item Avaliado", placeholder="Ex: Extintor, Pia, Lixeira")
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
                "Foto_Binaria": foto # Guardamos a foto real
            })
            st.success("Item salvo! Vá para a aba Relatório para baixar.")

# --- 3. RELATÓRIOS ---
elif menu == "Baixar Relatório PDF":
    st.title("📄 Exportar Relatório")
    
    qtd = len(st.session_state['vistorias'])
    st.write(f"Você tem **{qtd} itens** vistoriados nesta sessão.")
    
    if qtd > 0:
        # Mostra prévia
        for item in st.session_state['vistorias']:
            with st.expander(f"{item['Item']} ({item['Setor']})"):
                st.write(f"**Status:** {item['Situação']}")
                st.write(f"**Obs:** {item['Obs']}")
                if item['Foto_Binaria']:
                    st.image(item['Foto_Binaria'], width=200)

        # Botão de Gerar PDF
        if st.button("Gerar PDF Agora"):
            try:
                pdf_bytes = gerar_pdf(st.session_state['vistorias'])
                
                st.download_button(
                    label="📥 Clique aqui para baixar o PDF",
                    data=pdf_bytes,
                    file_name=f"relatorio_vistoria_{date.today()}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")

    else:
        st.info("Faça algumas vistorias primeiro.")
