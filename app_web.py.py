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
import unicodedata
import os # Necessário para limpar arquivos temporários
from streamlit_option_menu import option_menu

# --- 1. CONFIGURAÇÃO GERAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"
INTERVALO_CHECK_ROBO = 60
ID_PASTA_DRIVE = "1tGVSqvuy6D_FFz6nES90zYRKd0Tmd2wQ"

# --- 2. CÉREBRO DE INTELIGÊNCIA (BASE DE CONHECIMENTO + TAREFAS) ---
DOC_INTELLIGENCE = {
    # ... (MANTENDO A MESMA BASE DE CONHECIMENTO DA VERSÃO ANTERIOR PARA NÃO PERDER A LÓGICA DE DOCS) ...
    "Alvará de Funcionamento": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Renovação", "Taxa"]},
    "DEFAULT": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Verificar validade"]}
}
# (Simplifiquei aqui para caber, mas o código real usa a base completa que já definimos)
LISTA_TIPOS_DOCUMENTOS = ["Outros", "Alvará de Funcionamento", "Licença Sanitária", "Corpo de Bombeiros"] # Exemplo simplificado

# --- AUTO-REFRESH (Aumentado para evitar perder dados da vistoria) ---
components.html("""
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 600000); // 10 minutos
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

def normalizar_texto(texto):
    if texto is None: return ""
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto)) if unicodedata.category(c) != 'Mn').lower()

# --- FUNÇÃO GERADORA DE RELATÓRIO PDF INTELIGENTE (LOCAL) ---
class RelatorioPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Relatório Técnico de Vistoria - LegalizaHealth', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def gerar_pdf_vistoria_completo(itens_vistoria):
    pdf = RelatorioPDF()
    pdf.add_page()
    
    # --- CAPA E RESUMO ---
    pdf.set_font("Arial", "B", 12)
    total = len(itens_vistoria)
    criticos = sum(1 for i in itens_vistoria if i['Gravidade'] == 'CRÍTICO')
    altos = sum(1 for i in itens_vistoria if i['Gravidade'] == 'Alto')
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, f"Resumo Executivo", 1, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Total de Itens Avaliados: {total}", 0, 1)
    
    # Cores condicionais texto
    pdf.set_text_color(200, 0, 0) # Vermelho
    pdf.cell(0, 8, f"Itens Críticos: {criticos}", 0, 1)
    pdf.set_text_color(255, 140, 0) # Laranja
    pdf.cell(0, 8, f"Itens de Alto Risco: {altos}", 0, 1)
    pdf.set_text_color(0, 0, 0) # Preto
    pdf.ln(10)

    # --- ITENS ---
    for idx, item in enumerate(itens_vistoria):
        # Quebra de página inteligente se estiver no fim
        if pdf.get_y() > 250: pdf.add_page()
        
        # Título do Item com Cor de Fundo baseada no Risco
        if item['Gravidade'] == 'CRÍTICO': pdf.set_fill_color(255, 200, 200)
        elif item['Gravidade'] == 'Alto': pdf.set_fill_color(255, 230, 200)
        else: pdf.set_fill_color(230, 255, 230)
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 10, f"#{idx+1} - {item['Local']} | {item['Item']}", 1, 1, 'L', fill=True)
        
        # Detalhes
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 6, f"Situação: {item['Situação']}\nGravidade: {item['Gravidade']}\nObservações: {item['Obs']}")
        pdf.ln(2)
        
        # --- GALERIA DE FOTOS ---
        # Salva fotos temporariamente para inserir no PDF
        if item['Fotos']:
            x_start = 10
            y_start = pdf.get_y()
            img_w = 45
            img_h = 45
            
            for i, foto_bytes in enumerate(item['Fotos']):
                try:
                    # Cria arquivo temporário
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                        t.write(foto_bytes)
                        temp_path = t.name
                    
                    # Controla posição (3 fotos por linha)
                    if x_start + img_w > 200:
                        x_start = 10
                        y_start += img_h + 5
                        if y_start > 250: # Nova página se estourar
                            pdf.add_page()
                            y_start = 20
                    
                    pdf.image(temp_path, x=x_start, y=y_start, w=img_w, h=img_h)
                    x_start += img_w + 5
                    
                    # Limpa temp
                    os.unlink(temp_path)
                except: pass
            
            # Ajusta cursor para baixo das imagens
            pdf.set_y(y_start + img_h + 10)
        else:
            pdf.ln(5)
            
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

    return bytes(pdf.output(dest='S'))

# --- INTERFACE ---
if 'sessao_vistoria' not in st.session_state: st.session_state['sessao_vistoria'] = []
if 'fotos_temp' not in st.session_state: st.session_state['fotos_temp'] = []

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    
    menu = option_menu(
        menu_title=None,
        options=["Painel Geral", "Gestão de Docs", "Vistoria Mobile", "Relatórios"],
        icons=["speedometer2", "folder-check", "camera-fill", "file-pdf"],
        menu_icon="cast",
        default_index=2, # Começa na vistoria para facilitar
    )
    st.caption("v43.0 - Relatório PDF Instantâneo")

# --- TELAS ---
# (Omiti as telas Painel Geral e Gestão de Docs para focar na Vistoria, mas elas continuam existindo no seu código original)
# ... Código das outras telas aqui ...

if menu == "Painel Geral":
    st.title("Painel Geral")
    st.info("Funcionalidades mantidas (código omitido para brevidade na resposta, mantenha o seu anterior).")

elif menu == "Gestão de Docs":
    st.title("Gestão de Docs")
    st.info("Funcionalidades mantidas (código omitido para brevidade na resposta, mantenha o seu anterior).")

elif menu == "Vistoria Mobile":
    st.title("📋 Vistoria & Relatório Instantâneo")
    
    # --- BARRA DE PROGRESSO DA SESSÃO ---
    qtd_itens = len(st.session_state['sessao_vistoria'])
    st.progress(min(qtd_itens * 5, 100), text=f"Itens no Relatório Atual: {qtd_itens}")

    c_form, c_lista = st.columns([1, 1.2])

    with c_form:
        st.subheader("1. Coletar Dados")
        with st.container(border=True):
            # 1. LOCALIZAÇÃO E ITEM
            local = st.selectbox("Local / Setor", ["Recepção", "Triagem", "Consultório", "Raio-X", "UTI", "Expurgo", "Cozinha", "DML", "Farmácia", "Almoxarifado", "Externo"])
            item_nome = st.text_input("Item Avaliado", placeholder="Ex: Extintor, Infiltração, Lixo...")
            
            # 2. STATUS E RISCO
            c1, c2 = st.columns(2)
            situacao = c1.radio("Situação", ["✅ Conforme", "❌ Irregular", "⚠️ Atenção"], horizontal=False)
            gravidade = c2.select_slider("Risco / Gravidade", options=["Baixo", "Médio", "Alto", "CRÍTICO"], value="Baixo")
            
            # 3. OBSERVAÇÃO (COM PLACEHOLDER DE VOZ)
            obs = st.text_area("Observações", placeholder="Descreva o problema ou clique no microfone do seu teclado para ditar...")
            
            # 4. FOTOS (ACUMULATIVAS PARA O ITEM)
            st.write("📸 Evidências (Fotos)")
            foto_input = st.camera_input("Tirar Foto")
            
            # Lógica de acumular fotos temporárias para este item específico
            if foto_input:
                # Evita duplicatas exatas do buffer da camera
                if not st.session_state['fotos_temp'] or foto_input.getvalue() != st.session_state['fotos_temp'][-1]:
                    st.session_state['fotos_temp'].append(foto_input.getvalue())
                    st.toast("Foto anexada!")
            
            # Mostra miniaturas
            if st.session_state['fotos_temp']:
                st.image([x for x in st.session_state['fotos_temp']], width=80, caption=[f"Foto {i+1}" for i in range(len(st.session_state['fotos_temp']))])
                if st.button("Limpar Fotos do Item", type="secondary"):
                    st.session_state['fotos_temp'] = []
                    st.rerun()

            st.markdown("---")
            
            # 5. ADICIONAR AO RELATÓRIO
            btn_add = st.button("➕ ADICIONAR ITEM AO RELATÓRIO", type="primary", use_container_width=True)
            
            if btn_add:
                if not item_nome:
                    st.error("Digite o nome do item avaliado.")
                else:
                    novo_registro = {
                        "Local": local,
                        "Item": item_nome,
                        "Situação": situacao,
                        "Gravidade": gravidade,
                        "Obs": obs,
                        "Fotos": st.session_state['fotos_temp'].copy(), # Copia a lista de bytes
                        "Hora": datetime.now().strftime("%H:%M")
                    }
                    st.session_state['sessao_vistoria'].append(novo_registro)
                    st.session_state['fotos_temp'] = [] # Reseta fotos para o próximo item
                    st.toast(f"Item '{item_nome}' adicionado!", icon="📝")
                    time.sleep(0.5)
                    st.rerun()

    with c_lista:
        st.subheader("2. Revisar e Baixar")
        
        if len(st.session_state['sessao_vistoria']) == 0:
            st.info("Nenhum item coletado ainda. Comece ao lado! 👈")
        else:
            # MOSTRA LISTA DE ITENS
            for i, reg in enumerate(st.session_state['sessao_vistoria']):
                cor_borda = "red" if reg['Gravidade'] == "CRÍTICO" else "orange" if reg['Gravidade'] == "Alto" else "green"
                with st.expander(f"#{i+1} {reg['Item']} ({reg['Local']}) - {reg['Gravidade']}", expanded=False):
                    st.write(f"**Situação:** {reg['Situação']}")
                    st.write(f"**Obs:** {reg['Obs']}")
                    st.write(f"**Fotos:** {len(reg['Fotos'])}")
                    if st.button(f"🗑️ Remover Item {i+1}", key=f"del_{i}"):
                        st.session_state['sessao_vistoria'].pop(i)
                        st.rerun()
            
            st.markdown("---")
            c_down, c_clear = st.columns([2, 1])
            
            # BOTÃO DE DOWNLOAD DO PDF
            with c_down:
                pdf_bytes = gerar_pdf_vistoria_completo(st.session_state['sessao_vistoria'])
                nome_arq = f"Relatorio_Vistoria_{datetime.now().strftime('%d-%m-%H%M')}.pdf"
                st.download_button(
                    label="📄 BAIXAR RELATÓRIO PDF AGORA",
                    data=pdf_bytes,
                    file_name=nome_arq,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            
            # BOTÃO DE LIMPAR TUDO
            with c_clear:
                if st.button("🗑️ Limpar Tudo", type="secondary", use_container_width=True):
                    st.session_state['sessao_vistoria'] = []
                    st.session_state['fotos_temp'] = []
                    st.rerun()

elif menu == "Relatórios":
    st.title("Histórico de Relatórios")
    st.info("Aqui você pode consultar relatórios antigos salvos no Banco de Dados (se houver conexão).")
