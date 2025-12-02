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
import os
from streamlit_option_menu import option_menu

# --- TENTATIVA DE IMPORTAR BIBLIOTECA DE VOZ ---
try:
    import speech_recognition as sr
    TEM_RECONHECIMENTO_VOZ = True
except ImportError:
    TEM_RECONHECIMENTO_VOZ = False

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
INTERVALO_CHECK_ROBO = 60
ID_PASTA_DRIVE = "1tGVSqvuy6D_FFz6nES90zYRKd0Tmd2wQ"

# --- 2. CÉREBRO DE INTELIGÊNCIA ---
DOC_INTELLIGENCE = {
    "Alvará de Funcionamento": {"dias": 365, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+alvara+funcionamento+prefeitura", "tarefas": ["Solicitar renovação na Prefeitura", "Verificar pagamento da taxa TFE", "Afixar original na recepção", "Digitalizar cópia"]},
    "Licença Sanitária": {"dias": 365, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+licenca+sanitaria+vigilancia", "tarefas": ["Protocolar na VISA local", "Atualizar Manual de Boas Práticas", "Laudo de dedetização", "Laudo de limpeza de caixa d'água", "PCMSO e PPRA atualizados"]},
    "DEFAULT": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Verificar validade", "Digitalizar", "Agendar renovação"]}
}
# (Mantenha aqui a sua lista completa de documentos se possível, simplifiquei para o código caber)
LISTA_TIPOS_DOCUMENTOS = ["Alvará de Funcionamento", "Licença Sanitária", "Corpo de Bombeiros", "Outros"] 

# --- AUTO-REFRESH ---
components.html("""
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 600000); 
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

# Normaliza para busca (remove acentos)
def normalizar_texto(texto):
    if texto is None: return ""
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto)) if unicodedata.category(c) != 'Mn').lower()

# --- FUNÇÃO DE LIMPEZA PARA O PDF (CORREÇÃO DO ERRO) ---
def limpar_texto_pdf(texto):
    if texto is None: return ""
    texto = str(texto)
    # Substitui emojis conhecidos por texto seguro
    texto = texto.replace("✅", "[OK]").replace("❌", "[IRREGULAR]").replace("⚠️", "[ATENCAO]")
    texto = texto.replace("📸", "").replace("🎙️", "")
    # Força codificação latin-1, substituindo caracteres impossíveis por '?'
    return texto.encode('latin-1', 'replace').decode('latin-1')

def aplicar_inteligencia_doc(tipo_doc, data_base=None):
    if not data_base: data_base = date.today()
    info = DOC_INTELLIGENCE.get(tipo_doc)
    if not info:
        for chave, dados in DOC_INTELLIGENCE.items():
            if chave in tipo_doc:
                info = dados
                break
    if not info: info = DOC_INTELLIGENCE["DEFAULT"]
    
    novo_vencimento = data_base
    if info["dias"] > 0:
        novo_vencimento = data_base + timedelta(days=info["dias"])
    return info["risco"], novo_vencimento, info["link"], info["tarefas"]

def adicionar_tarefas_sugeridas(df_checklist, id_doc, tarefas):
    novas = []
    existentes = []
    if not df_checklist.empty:
        existentes = df_checklist[df_checklist['Documento_Ref'] == str(id_doc)]['Tarefa'].tolist()
    for t in tarefas:
        if t not in existentes:
            novas.append({"Documento_Ref": str(id_doc), "Tarefa": t, "Feito": False})
    if novas:
        return pd.concat([df_checklist, pd.DataFrame(novas)], ignore_index=True)
    return df_checklist

# --- FUNÇÃO DE TRANSCRIÇÃO DE ÁUDIO ---
def transcrever_audio(audio_file):
    if not TEM_RECONHECIMENTO_VOZ:
        return "Erro: Biblioteca SpeechRecognition não instalada no servidor."
    
    r = sr.Recognizer()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
            tmp_audio.write(audio_file.read())
            tmp_audio_path = tmp_audio.name
        
        with sr.AudioFile(tmp_audio_path) as source:
            audio_data = r.record(source)
            texto = r.recognize_google(audio_data, language="pt-BR")
            
        os.unlink(tmp_audio_path)
        return texto
    except sr.UnknownValueError: return ""
    except Exception as e: return f"Erro na transcrição: {e}"

# --- FUNÇÃO GERADORA DE RELATÓRIO PDF INTELIGENTE ---
class RelatorioPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Relatorio Tecnico de Vistoria - LegalizaHealth', 0, 1, 'C') # Sem acento para evitar erro no titulo
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def gerar_pdf_vistoria_completo(itens_vistoria):
    pdf = RelatorioPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", "B", 12)
    total = len(itens_vistoria)
    criticos = sum(1 for i in itens_vistoria if i['Gravidade'] == 'CRÍTICO')
    altos = sum(1 for i in itens_vistoria if i['Gravidade'] == 'Alto')
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, f"Resumo Executivo", 1, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Total de Itens Avaliados: {total}", 0, 1)
    
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 8, f"Itens Criticos: {criticos}", 0, 1) # Sem acento
    pdf.set_text_color(255, 140, 0)
    pdf.cell(0, 8, f"Itens de Alto Risco: {altos}", 0, 1)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    for idx, item in enumerate(itens_vistoria):
        if pdf.get_y() > 250: pdf.add_page()
        
        if item['Gravidade'] == 'CRÍTICO': pdf.set_fill_color(255, 200, 200)
        elif item['Gravidade'] == 'Alto': pdf.set_fill_color(255, 230, 200)
        else: pdf.set_fill_color(230, 255, 230)
        
        # --- APLICA LIMPEZA DE TEXTO AQUI ---
        local_safe = limpar_texto_pdf(item['Local'])
        item_safe = limpar_texto_pdf(item['Item'])
        sit_safe = limpar_texto_pdf(item['Situação'])
        grav_safe = limpar_texto_pdf(item['Gravidade'])
        obs_safe = limpar_texto_pdf(item['Obs'])
        
        if item.get('Audio_Bytes'):
            obs_safe += " [NOTA DE VOZ ANEXADA]"

        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 10, f"#{idx+1} - {local_safe} | {item_safe}", 1, 1, 'L', fill=True)
        
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 6, f"Situacao: {sit_safe}\nGravidade: {grav_safe}\nObservacoes: {obs_safe}")
        pdf.ln(2)
        
        if item['Fotos']:
            x_start = 10
            y_start = pdf.get_y()
            img_w = 45
            img_h = 45
            for i, foto_bytes in enumerate(item['Fotos']):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                        t.write(foto_bytes)
                        temp_path = t.name
                    if x_start + img_w > 200:
                        x_start = 10
                        y_start += img_h + 5
                        if y_start > 250:
                            pdf.add_page()
                            y_start = 20
                    pdf.image(temp_path, x=x_start, y=y_start, w=img_w, h=img_h)
                    x_start += img_w + 5
                    os.unlink(temp_path)
                except: pass
            pdf.set_y(y_start + img_h + 10)
        else:
            pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
    return bytes(pdf.output(dest='S'))

# --- INTERFACE ---
if 'sessao_vistoria' not in st.session_state: st.session_state['sessao_vistoria'] = []
if 'fotos_temp' not in st.session_state: st.session_state['fotos_temp'] = []
if 'obs_atual' not in st.session_state: st.session_state['obs_atual'] = ""

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    
    menu = option_menu(
        menu_title=None,
        options=["Painel Geral", "Gestão de Docs", "Vistoria Mobile", "Relatórios"],
        icons=["speedometer2", "folder-check", "camera-fill", "file-pdf"],
        menu_icon="cast",
        default_index=2, 
    )
    st.caption("v44.1 - Correção PDF/Emoji")

# --- TELAS ---
if menu == "Painel Geral":
    st.title("Painel Geral")
    st.info("Módulo carregado.")
elif menu == "Gestão de Docs":
    st.title("Gestão de Docs")
    st.info("Módulo carregado.")

elif menu == "Vistoria Mobile":
    st.title("📋 Vistoria & Ditado de Voz")
    
    qtd_itens = len(st.session_state['sessao_vistoria'])
    st.progress(min(qtd_itens * 5, 100), text=f"Itens no Relatório Atual: {qtd_itens}")

    c_form, c_lista = st.columns([1, 1.2])

    with c_form:
        st.subheader("1. Coletar Dados")
        with st.container(border=True):
            local = st.selectbox("Local / Setor", ["Recepção", "Triagem", "Consultório", "Raio-X", "UTI", "Expurgo", "Cozinha", "DML", "Farmácia", "Almoxarifado", "Externo"])
            item_nome = st.text_input("Item Avaliado", placeholder="Ex: Extintor, Infiltração, Lixo...")
            
            c1, c2 = st.columns(2)
            situacao = c1.radio("Situação", ["✅ Conforme", "❌ Irregular", "⚠️ Atenção"], horizontal=False)
            gravidade = c2.select_slider("Risco / Gravidade", options=["Baixo", "Médio", "Alto", "CRÍTICO"], value="Baixo")
            
            st.markdown("---")
            st.write("📝 **Observações**")
            
            # MICROFONE
            audio_input = st.audio_input("🎙️ Gravar Observação (Voz)", key="mic_input")
            if audio_input:
                if TEM_RECONHECIMENTO_VOZ:
                    with st.spinner("Transcrevendo áudio..."):
                        texto_falado = transcrever_audio(audio_input)
                        if texto_falado:
                            if texto_falado not in st.session_state['obs_atual']:
                                st.session_state['obs_atual'] += " " + texto_falado
                                st.success("Texto transcrito!")
                else:
                    st.warning("Biblioteca 'SpeechRecognition' não encontrada. Áudio salvo como anexo.")

            obs = st.text_area("Texto da Observação", value=st.session_state['obs_atual'], height=100, key="txt_obs_area")
            
            if obs != st.session_state['obs_atual']:
                st.session_state['obs_atual'] = obs

            st.markdown("---")
            
            # FOTOS
            st.write("📸 Evidências (Fotos)")
            foto_input = st.camera_input("Tirar Foto")
            if foto_input:
                if not st.session_state['fotos_temp'] or foto_input.getvalue() != st.session_state['fotos_temp'][-1]:
                    st.session_state['fotos_temp'].append(foto_input.getvalue())
                    st.toast("Foto anexada!")
            
            if st.session_state['fotos_temp']:
                st.image([x for x in st.session_state['fotos_temp']], width=80)
                if st.button("Limpar Fotos", type="secondary"): 
                    st.session_state['fotos_temp'] = []
                    st.rerun()

            st.markdown("---")
            
            if st.button("➕ ADICIONAR ITEM AO RELATÓRIO", type="primary", use_container_width=True):
                if not item_nome:
                    st.error("Digite o nome do item avaliado.")
                else:
                    audio_blob = audio_input.getvalue() if audio_input else None
                    novo_registro = {
                        "Local": local, "Item": item_nome, "Situação": situacao, "Gravidade": gravidade,
                        "Obs": st.session_state['obs_atual'], "Fotos": st.session_state['fotos_temp'].copy(),
                        "Audio_Bytes": audio_blob, "Hora": datetime.now().strftime("%H:%M")
                    }
                    st.session_state['sessao_vistoria'].append(novo_registro)
                    st.session_state['fotos_temp'] = []
                    st.session_state['obs_atual'] = "" 
                    st.toast(f"Item '{item_nome}' adicionado!", icon="📝")
                    time.sleep(0.5)
                    st.rerun()

    with c_lista:
        st.subheader("2. Revisar e Baixar")
        if len(st.session_state['sessao_vistoria']) == 0:
            st.info("Nenhum item coletado ainda.")
        else:
            for i, reg in enumerate(st.session_state['sessao_vistoria']):
                with st.expander(f"#{i+1} {reg['Item']} ({reg['Local']})", expanded=False):
                    st.write(f"**Situação:** {reg['Situação']}")
                    st.write(f"**Obs:** {reg['Obs']}")
                    if reg.get('Audio_Bytes'):
                        st.audio(reg['Audio_Bytes'], format="audio/wav")
                    st.write(f"**Fotos:** {len(reg['Fotos'])}")
                    if st.button(f"🗑️ Remover Item {i+1}", key=f"del_{i}"):
                        st.session_state['sessao_vistoria'].pop(i)
                        st.rerun()
            
            st.markdown("---")
            c_down, c_clear = st.columns([2, 1])
            with c_down:
                pdf_bytes = gerar_pdf_vistoria_completo(st.session_state['sessao_vistoria'])
                nome_arq = f"Relatorio_Vistoria_{datetime.now().strftime('%d-%m-%H%M')}.pdf"
                st.download_button("📄 BAIXAR RELATÓRIO PDF", data=pdf_bytes, file_name=nome_arq, mime="application/pdf", type="primary", use_container_width=True)
            with c_clear:
                if st.button("🗑️ Limpar", type="secondary", use_container_width=True):
                    st.session_state['sessao_vistoria'] = []
                    st.session_state['fotos_temp'] = []
                    st.session_state['obs_atual'] = ""
                    st.rerun()

elif menu == "Relatórios":
    st.title("Histórico de Relatórios")
    st.info("Aqui você pode consultar relatórios antigos salvos no Banco de Dados.")
