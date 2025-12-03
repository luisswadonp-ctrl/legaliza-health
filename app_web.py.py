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
import zipfile
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

# --- 2. CÉREBRO DE INTELIGÊNCIA DINÂMICA (CONTEXTO) ---
# Aqui definimos as regras para cada NICHO de mercado.
CONTEXT_DATA = {
    "🏥 Hospital / Clínica": {
        "setores": ["Recepção", "Triagem", "Consultório", "Raio-X", "UTI", "Expurgo", "Cozinha", "DML", "Farmácia", "Almoxarifado", "Centro Cirúrgico", "Externo"],
        "sugestoes": {
            "UTI": ["Grade do leito baixada", "Sinalização de higienização faltante", "Equipamento sem calibração", "Lixo infectante aberto"],
            "Farmácia": ["Medicamento vencido", "Temperatura ambiente alta", "Controle de psicotrópicos falho", "Umidade excessiva"],
            "Expurgo": ["Descarte incorreto de perfurocortantes", "Sacos de lixo misturados", "Ambiente sujo", "Cheiro forte"],
            "Raio-X": ["Luz vermelha queimada", "Porta sem blindagem", "Dosímetro ausente", "Avental de chumbo danificado"],
            "Cozinha": ["Temperatura da Geladeira Inadequada", "Lixo sem tampa/pedal", "Ausência de touca/EPI", "Alimentos sem etiqueta"],
            "DEFAULT": ["Lâmpada queimada", "Infiltração", "Piso quebrado", "Extintor vencido"]
        }
    },
    "🏭 Indústria / Fábrica": {
        "setores": ["Linha de Produção", "Estoque de Matéria Prima", "Expedição", "Refeitório", "Vestiário", "Caldeiras", "Manutenção", "Administrativo"],
        "sugestoes": {
            "Linha de Produção": ["Operador sem EPI (Óculos/Luva)", "Máquina sem proteção (NR-12)", "Fios expostos", "Área de circulação obstruída"],
            "Estoque de Matéria Prima": ["Empilhamento excessivo", "Material sem identificação", "Pallets quebrados", "Sinalização de solo apagada"],
            "Caldeiras": ["Vazamento de vapor", "Manômetro quebrado", "Válvula de segurança travada", "Ausência de isolamento térmico"],
            "Refeitório": ["Piso escorregadio", "Restos de comida expostos", "Bebedouro sujo"],
            "DEFAULT": ["Extintor obstruído", "Sinalização de emergência apagada", "Lixo no chão", "Ruído excessivo"]
        }
    },
    "🛒 Mercado / Varejo": {
        "setores": ["Frente de Caixa", "Gôndolas/Corredor", "Açougue", "Padaria", "Hortifruti", "Estoque", "Câmara Fria", "Doca de Recebimento"],
        "sugestoes": {
            "Açougue": ["Temperatura do balcão alta", "Carne sem etiqueta de validade", "Facas fora do suporte", "Uniforme sujo"],
            "Padaria": ["Formas sujas", "Farinha no chão", "Validade do fermento vencida", "Ausência de tela milimétrica"],
            "Gôndolas/Corredor": ["Produto vencido na prateleira", "Preço ausente", "Produto violado", "Carrinho obstruindo passagem"],
            "Câmara Fria": ["Gelo acumulado no evaporador", "Porta não veda", "Temperatura acima do ideal", "Alimentos no chão (sem pallet)"],
            "DEFAULT": ["Piso molhado sem placa", "Extintor vencido", "Iluminação fraca", "Ar condicionado sujo"]
        }
    },
    "🏫 Escola / Educação": {
        "setores": ["Sala de Aula", "Pátio", "Cantina", "Banheiros", "Biblioteca", "Laboratório", "Secretaria"],
        "sugestoes": {
            "Sala de Aula": ["Carteira quebrada", "Lousa danificada", "Ventilador oscilando", "Fiação exposta"],
            "Pátio": ["Piso irregular (risco de queda)", "Brinquedo enferrujado", "Água parada"],
            "Laboratório": ["Reagentes vencidos", "Vidraria quebrada", "Ausência de chuveiro de emergência"],
            "DEFAULT": ["Extintor vencido", "Limpeza precária", "Lâmpada queimada"]
        }
    }
}

# Base de Documentos (Resumida para o código caber)
DOC_INTELLIGENCE = {
    "Alvará de Funcionamento": {"dias": 365, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+alvara+funcionamento+prefeitura", "tarefas": ["Renovação", "Taxa"]},
    "Licença Sanitária": {"dias": 365, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+licenca+sanitaria+vigilancia", "tarefas": ["Protocolo VISA", "Manual Boas Práticas"]},
    "Corpo de Bombeiros": {"dias": 1095, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+avcb+bombeiros", "tarefas": ["Extintores", "Hidrantes"]},
    "DEFAULT": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Verificar validade"]}
}
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

def normalizar_texto(texto):
    if texto is None: return ""
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto)) if unicodedata.category(c) != 'Mn').lower()

def limpar_texto_pdf(texto):
    if texto is None: return ""
    texto = str(texto)
    texto = texto.replace("✅", "[OK]").replace("❌", "[IRREGULAR]").replace("⚠️", "[ATENCAO]")
    return texto.encode('latin-1', 'replace').decode('latin-1')

def aplicar_inteligencia_doc(tipo_doc, data_base=None):
    if not data_base: data_base = date.today()
    info = DOC_INTELLIGENCE.get(tipo_doc)
    if not info: info = DOC_INTELLIGENCE["DEFAULT"]
    novo_vencimento = data_base
    if info["dias"] > 0: novo_vencimento = data_base + timedelta(days=info["dias"])
    return info["risco"], novo_vencimento, info["link"], info["tarefas"]

def adicionar_tarefas_sugeridas(df_checklist, id_doc, tarefas):
    novas = []
    existentes = []
    if not df_checklist.empty:
        existentes = df_checklist[df_checklist['Documento_Ref'] == str(id_doc)]['Tarefa'].tolist()
    for t in tarefas:
        if t not in existentes:
            novas.append({"Documento_Ref": str(id_doc), "Tarefa": t, "Feito": False})
    if novas: return pd.concat([df_checklist, pd.DataFrame(novas)], ignore_index=True)
    return df_checklist

# --- FUNÇÃO DE TRANSCRIÇÃO ---
def transcrever_audio(audio_file):
    if not TEM_RECONHECIMENTO_VOZ: return "Erro: Biblioteca não instalada."
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
    except: return ""

# --- GERADOR DE ZIP ---
class RelatorioPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Relatorio Tecnico - LegalizaHealth', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Data: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def gerar_pacote_zip_completo(itens_vistoria, tipo_estabelecimento):
    pdf = RelatorioPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    
    total = len(itens_vistoria)
    criticos = sum(1 for i in itens_vistoria if i['Gravidade'] == 'CRÍTICO')
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, f"Resumo Executivo - {limpar_texto_pdf(tipo_estabelecimento)}", 1, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Total de Itens: {total} | Criticos: {criticos}", 0, 1)
    pdf.ln(5)

    audios_para_zip = []

    for idx, item in enumerate(itens_vistoria):
        if pdf.get_y() > 250: pdf.add_page()
        
        if item['Gravidade'] == 'CRÍTICO': pdf.set_fill_color(255, 200, 200)
        elif item['Gravidade'] == 'Alto': pdf.set_fill_color(255, 230, 200)
        else: pdf.set_fill_color(230, 255, 230)
        
        local_safe = limpar_texto_pdf(item['Local'])
        item_safe = limpar_texto_pdf(item['Item'])
        obs_safe = limpar_texto_pdf(item['Obs'])
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 10, f"#{idx+1} - {local_safe} | {item_safe}", 1, 1, 'L', fill=True)
        
        pdf.set_font("Arial", "", 10)
        info_extra = ""
        
        if item.get('Audio_Bytes'):
            nome_audio = f"Audio_Item_{idx+1}.wav"
            audios_para_zip.append((nome_audio, item['Audio_Bytes']))
            info_extra = f" [AUDIO ANEXO: {nome_audio}]"

        pdf.multi_cell(0, 6, f"Situacao: {limpar_texto_pdf(item['Situação'])}\nGravidade: {limpar_texto_pdf(item['Gravidade'])}\nObs: {obs_safe}{info_extra}")
        pdf.ln(2)
        
        if item['Fotos']:
            x_start = 10; y_start = pdf.get_y(); img_w = 45; img_h = 45
            for i, foto_bytes in enumerate(item['Fotos']):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as t:
                        t.write(foto_bytes); temp_path = t.name
                    if x_start + img_w > 200:
                        x_start = 10; y_start += img_h + 5
                        if y_start > 250: pdf.add_page(); y_start = 20
                    pdf.image(temp_path, x=x_start, y=y_start, w=img_w, h=img_h)
                    x_start += img_w + 5; os.unlink(temp_path)
                except: pass
            pdf.set_y(y_start + img_h + 10)
        else: pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        zip_file.writestr(f"Relatorio_Vistoria_{datetime.now().strftime('%d-%m')}.pdf", pdf_bytes)
        for nome_arq, dados_audio in audios_para_zip:
            if hasattr(dados_audio, 'getvalue'): zip_file.writestr(nome_arq, dados_audio.getvalue())
            else: zip_file.writestr(nome_arq, dados_audio)
                
    return zip_buffer.getvalue()

# --- INTERFACE ---
if 'sessao_vistoria' not in st.session_state: st.session_state['sessao_vistoria'] = []
if 'fotos_temp' not in st.session_state: st.session_state['fotos_temp'] = []
if 'obs_atual' not in st.session_state: st.session_state['obs_atual'] = ""
# Variável para guardar o tipo de estabelecimento da sessão
if 'tipo_estabelecimento_atual' not in st.session_state: st.session_state['tipo_estabelecimento_atual'] = "🏥 Hospital / Clínica"

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    menu = option_menu(menu_title=None, options=["Painel Geral", "Gestão de Docs", "Vistoria Mobile", "Relatórios"], icons=["speedometer2", "folder-check", "camera-fill", "file-pdf"], default_index=2)
    st.caption("v46.0 - Contexto Multi-Setor")

# --- TELAS ---
if menu == "Painel Geral":
    st.title("Painel Geral")
    st.info("Módulo carregado.")
elif menu == "Gestão de Docs":
    st.title("Gestão de Docs")
    st.info("Módulo carregado.")

elif menu == "Vistoria Mobile":
    st.title("📋 Vistoria Inteligente")
    
    # --- SELETOR DE CONTEXTO (IMPORTANTE: Fica no topo) ---
    st.write("📍 **Configuração da Visita**")
    tipo_estab = st.selectbox(
        "Qual o tipo de estabelecimento?", 
        options=list(CONTEXT_DATA.keys()),
        index=list(CONTEXT_DATA.keys()).index(st.session_state['tipo_estabelecimento_atual'])
    )
    # Atualiza sessão se mudar
    if tipo_estab != st.session_state['tipo_estabelecimento_atual']:
        st.session_state['tipo_estabelecimento_atual'] = tipo_estab
        st.toast(f"Modo {tipo_estab} ativado!", icon="🔄")
        time.sleep(0.5)
        st.rerun()

    st.markdown("---")

    qtd_itens = len(st.session_state['sessao_vistoria'])
    st.progress(min(qtd_itens * 5, 100), text=f"Itens no Relatório: {qtd_itens}")

    c_form, c_lista = st.columns([1, 1.2])

    with c_form:
        st.subheader("1. Coleta Inteligente")
        with st.container(border=True):
            # CARREGA DADOS DO CONTEXTO SELECIONADO
            contexto_atual = CONTEXT_DATA[st.session_state['tipo_estabelecimento_atual']]
            lista_setores = contexto_atual["setores"]
            mapa_sugestoes = contexto_atual["sugestoes"]

            local = st.selectbox("Local / Setor", lista_setores)
            
            # --- SUGESTÕES DINÂMICAS ---
            # Pega sugestões específicas do setor OU usa as DEFAULT do contexto
            sugestoes = mapa_sugestoes.get(local, mapa_sugestoes["DEFAULT"])
            
            if sugestoes:
                st.caption(f"⚡ Problemas comuns em {local} (Clique para preencher):")
                cols_sug = st.columns(2)
                for i, sug in enumerate(sugestoes):
                    if cols_sug[i % 2].button(sug, key=f"sug_{i}", use_container_width=True):
                        st.session_state['item_temp_nome'] = sug
                        st.rerun()
            
            val_item = st.session_state.get('item_temp_nome', "")
            item_nome = st.text_input("Item Avaliado", value=val_item, key="input_item_nome")
            if item_nome != val_item: st.session_state['item_temp_nome'] = item_nome

            c1, c2 = st.columns(2)
            situacao = c1.radio("Situação", ["✅ Conforme", "❌ Irregular", "⚠️ Atenção"], horizontal=False)
            gravidade = c2.select_slider("Risco", options=["Baixo", "Médio", "Alto", "CRÍTICO"], value="Baixo")
            
            st.markdown("---")
            st.write("📝 **Observação & Voz**")
            audio_input = st.audio_input("🎙️ Gravar", key="mic_input")
            
            if audio_input and TEM_RECONHECIMENTO_VOZ:
                txt = transcrever_audio(audio_input)
                if txt and txt not in st.session_state['obs_atual']:
                    st.session_state['obs_atual'] += " " + txt
            
            obs = st.text_area("Texto", value=st.session_state['obs_atual'], height=100)
            if obs != st.session_state['obs_atual']: st.session_state['obs_atual'] = obs

            st.markdown("---")
            st.write("📸 **Fotos**")
            foto_input = st.camera_input("Foto")
            if foto_input:
                if not st.session_state['fotos_temp'] or foto_input.getvalue() != st.session_state['fotos_temp'][-1]:
                    st.session_state['fotos_temp'].append(foto_input.getvalue())
            
            if st.session_state['fotos_temp']:
                st.image([x for x in st.session_state['fotos_temp']], width=80)
                if st.button("Limpar Fotos", type="secondary"): 
                    st.session_state['fotos_temp'] = []; st.rerun()

            st.markdown("---")
            if st.button("➕ ADICIONAR AO RELATÓRIO", type="primary", use_container_width=True):
                if not item_nome: st.error("Nome do item obrigatório.")
                else:
                    audio_blob = audio_input.getvalue() if audio_input else None
                    novo = {
                        "Local": local, "Item": item_nome, "Situação": situacao, "Gravidade": gravidade,
                        "Obs": st.session_state['obs_atual'], "Fotos": st.session_state['fotos_temp'].copy(),
                        "Audio_Bytes": audio_blob, "Hora": datetime.now().strftime("%H:%M")
                    }
                    st.session_state['sessao_vistoria'].append(novo)
                    st.session_state['fotos_temp'] = []
                    st.session_state['obs_atual'] = ""
                    st.session_state['item_temp_nome'] = "" 
                    st.toast("Item salvo!", icon="💾")
                    time.sleep(0.5); st.rerun()

    with c_lista:
        st.subheader("2. Pacote de Evidências")
        if not st.session_state['sessao_vistoria']:
            st.info("Lista vazia.")
        else:
            for i, reg in enumerate(st.session_state['sessao_vistoria']):
                with st.expander(f"#{i+1} {reg['Item']} ({reg['Local']})", expanded=False):
                    st.write(f"**Situação:** {reg['Situação']}")
                    if reg.get('Audio_Bytes'): st.audio(reg['Audio_Bytes'])
                    st.write(f"**Fotos:** {len(reg['Fotos'])}")
                    if st.button("Remover", key=f"del_{i}"):
                        st.session_state['sessao_vistoria'].pop(i); st.rerun()
            
            st.markdown("---")
            # PASSAMOS O TIPO DE ESTABELECIMENTO PARA O PDF
            zip_data = gerar_pacote_zip_completo(st.session_state['sessao_vistoria'], st.session_state['tipo_estabelecimento_atual'])
            nome_zip = f"Vistoria_{limpar_texto_pdf(st.session_state['tipo_estabelecimento_atual'])}_{datetime.now().strftime('%d-%m-%H%M')}.zip"
            
            st.download_button(
                label="📦 BAIXAR PACOTE COMPLETO (.ZIP)",
                data=zip_data,
                file_name=nome_zip,
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
            
            if st.button("Limpar Tudo", type="secondary", use_container_width=True):
                st.session_state['sessao_vistoria'] = []
                st.rerun()

elif menu == "Relatórios":
    st.title("Histórico de Relatórios")
    st.info("Aqui você pode consultar relatórios antigos salvos no Banco de Dados.")
