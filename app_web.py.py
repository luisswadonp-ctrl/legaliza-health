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

# --- 1. CONFIGURAÇÃO GERAL (MOBILE FIRST) ---
st.set_page_config(
    page_title="LegalizaHealth Pro", 
    page_icon="🏥", 
    layout="wide",
    initial_sidebar_state="collapsed" # COMEÇA FECHADO PARA DAR ESPAÇO NO CELULAR
)

TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"
INTERVALO_CHECK_ROBO = 60
ID_PASTA_DRIVE = "1tGVSqvuy6D_FFz6nES90zYRKd0Tmd2wQ"

# --- 2. CÉREBRO DE INTELIGÊNCIA DINÂMICA (NÍVEL SÊNIOR) ---
CONTEXT_DATA = {
    "🏥 Hospital / Clínica / Laboratório": {
        "setores": [
            "Recepção/Acessibilidade", "Consultório Indiferenciado", "Consultório Gineco/Uro", 
            "Sala de Procedimentos", "DML (Limpeza)", "Expurgo (Sujo)", "Esterilização (Limpo)", 
            "Abrigo de Resíduos", "Cozinha/Copa", "Farmácia/CAF", "Raio-X/Imagem", "UTI", "Centro Cirúrgico"
        ],
        "sugestoes": {
            "Recepção/Acessibilidade": [
                "Balcão de atendimento sem rebaixo PNE (NBR 9050)",
                "Sanitário PNE sem barras de apoio ou alarme de emergência",
                "Área de giro 1.50m no sanitário PNE obstruída",
                "Desnível de piso > 5mm sem rampa",
                "Bebedouro não acessível (altura incorreta)"
            ],
            "Consultório Indiferenciado": [
                "Ausência de lavatório para mãos (obrigatório)",
                "Torneira com acionamento manual (exige comando não manual)",
                "Piso/Parede com juntas ou rodapé não arredondado",
                "Mobiliário com superfície porosa (madeira não tratada)",
                "Lixeira sem acionamento por pedal"
            ],
            "Consultório Gineco/Uro": [
                "Sanitário anexo não acessível ou ausente",
                "Falta de área para troca de vestimenta",
                "Foco de luz auxiliar inoperante"
            ],
            "DML (Limpeza)": [
                "Tanque de lavagem único (necessário setorização)",
                "Ausência de ralo sifonado",
                "Armazenamento de saneantes sem estrado/pallet",
                "Ventilação mecânica ineficiente/ausente"
            ],
            "Expurgo (Sujo)": [
                "Cruzamento de fluxo limpo x sujo",
                "Ausência de pia de lavagem profunda (vazia clínica)",
                "Pistola de ar/água inoperante",
                "Bancada de madeira ou material poroso"
            ],
            "Esterilização (Limpo)": [
                "Autoclave sem registro de teste biológico/químico",
                "Barreira física entre área suja/limpa inexistente",
                "Ar condicionado sem controle de temperatura",
                "Armazenamento de estéreis próximo ao teto/piso"
            ],
            "Abrigo de Resíduos": [
                "Ausência de ponto de água e ralo",
                "Área não telada (acesso de vetores)",
                "Identificação de grupos (A, B, E) incorreta",
                "Porta sem abertura para ventilação (veneziana)"
            ],
            "Farmácia/CAF": [
                "Termohigrômetro não calibrado ou ausente",
                "Armário de controlados (Port. 344) sem chave/segurança",
                "Pallets de madeira (proibido em área limpa)",
                "Medicamentos encostados na parede/teto"
            ],
            "Raio-X/Imagem": [
                "Sinalização luminosa (luz vermelha) inoperante",
                "Visor plumbífero com falha de vedação",
                "Porta sem proteção radiológica (chumbo)",
                "Ausência de sinalização 'Risco de Radiação' e 'Grávidas'"
            ],
            "DEFAULT": [
                "Divergência entre Projeto (LTA) e Executado",
                "Extintor vencido ou obstruído",
                "Sinalização de rota de fuga fotoluminescente ausente",
                "Iluminação de emergência inoperante",
                "Certificado de dedetização vencido"
            ]
        }
    },
    "🏭 Indústria / Logística": {
        "setores": ["Linha de Produção", "Estoque/Almoxarifado", "Vestiários", "Refeitório", "Caldeiras/Compressor", "Área Externa"],
        "sugestoes": {
            "Linha de Produção": [
                "Máquinas sem proteção de partes móveis (NR-12)",
                "Área de circulação obstruída/sem demarcação",
                "Painel elétrico desobstruído ou sem tranca (NR-10)",
                "Iluminação insuficiente (Luxímetro)"
            ],
            "Estoque/Almoxarifado": [
                "Empilhamento acima da capacidade (risco de queda)",
                "Extintores obstruídos por mercadoria",
                "Estrutura de porta-pallets danificada",
                "Ausência de rota de fuga demarcada no chão"
            ],
            "Vestiários": [
                "Armários insuficientes para nº de funcionários (NR-24)",
                "Piso escorregadio/sem antiderrapante",
                "Ventilação inadequada"
            ],
            "DEFAULT": [
                "AVCB vencido ou não condizente com layout",
                "Ausência de SPDA (Para-raios) laudo",
                "Descarte de efluentes irregular"
            ]
        }
    },
    "🛒 Varejo de Alimentos (Mercado/Restaurante)": {
        "setores": ["Área de Venda", "Cozinha/Manipulação", "Estoque Seco", "Câmara Fria", "Saneantes", "Lixo"],
        "sugestoes": {
            "Cozinha/Manipulação": [
                "Fluxo cruzado (alimento cru x cozido)",
                "Ausência de pia exclusiva para lavagem de mãos",
                "Ausência de tela milimétrica nas janelas",
                "Luminárias sem proteção contra estilhaços"
            ],
            "Câmara Fria": [
                "Temperatura acima do permitido",
                "Gelo acumulado nos evaporadores/piso",
                "Alimentos armazenados diretamente no chão",
                "Porta não veda corretamente (borracha)"
            ],
            "DEFAULT": [
                "Licença Sanitária vencida",
                "Manual de Boas Práticas desatualizado",
                "Certificado de Limpeza de Caixa d'Água vencido"
            ]
        }
    }
}

# --- 2.1 BASE DE DOCUMENTOS ---
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
    texto = texto.replace("✅", "[OK]").replace("❌", "[NC]").replace("⚠️", "[!]")
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
        self.cell(0, 10, 'Relatorio de Vistoria Tecnica - Legalizacao', 0, 1, 'C')
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
    pdf.cell(0, 10, f"Resumo - {limpar_texto_pdf(tipo_estabelecimento)}", 1, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Total de Apontamentos: {total} | Pontos Criticos: {criticos}", 0, 1)
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
        pdf.multi_cell(0, 8, f"#{idx+1} - {local_safe}", 1, 'L', fill=True)
        
        pdf.set_font("Arial", "B", 10)
        pdf.multi_cell(0, 6, f"NC Identificada: {item_safe}")
        
        pdf.set_font("Arial", "", 10)
        info_extra = ""
        
        if item.get('Audio_Bytes'):
            nome_audio = f"Audio_Item_{idx+1}.wav"
            audios_para_zip.append((nome_audio, item['Audio_Bytes']))
            info_extra = f" [AUDIO ANEXO: {nome_audio}]"

        pdf.multi_cell(0, 6, f"Status: {limpar_texto_pdf(item['Situação'])}\nGravidade: {limpar_texto_pdf(item['Gravidade'])}\nDetalhes: {obs_safe}{info_extra}")
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
if 'tipo_estabelecimento_atual' not in st.session_state: st.session_state['tipo_estabelecimento_atual'] = "🏥 Hospital / Clínica / Laboratório"
# Controle de seleção das checkboxes para evitar reset
if 'checks_temp' not in st.session_state: st.session_state['checks_temp'] = {}

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    menu = option_menu(menu_title=None, options=["Painel Geral", "Gestão de Docs", "Vistoria Mobile", "Relatórios"], icons=["speedometer2", "folder-check", "camera-fill", "file-pdf"], default_index=2)
    st.caption("v49.0 - Mobile Sênior")

# --- TELAS ---
if menu == "Painel Geral":
    st.title("Painel Geral")
    st.info("Módulo carregado.")
elif menu == "Gestão de Docs":
    st.title("Gestão de Docs")
    st.info("Módulo carregado.")

elif menu == "Vistoria Mobile":
    st.title("📋 Vistoria Técnica")
    
    st.write("📍 **Contexto da Vistoria**")
    
    if st.session_state['tipo_estabelecimento_atual'] not in CONTEXT_DATA.keys():
        st.session_state['tipo_estabelecimento_atual'] = list(CONTEXT_DATA.keys())[0]
        
    tipo_estab = st.selectbox(
        "Tipo de Estabelecimento", 
        options=list(CONTEXT_DATA.keys()),
        index=list(CONTEXT_DATA.keys()).index(st.session_state['tipo_estabelecimento_atual'])
    )
    if tipo_estab != st.session_state['tipo_estabelecimento_atual']:
        st.session_state['tipo_estabelecimento_atual'] = tipo_estab
        st.session_state['checks_temp'] = {} # Limpa seleção se mudar contexto
        st.rerun()

    st.markdown("---")

    qtd_itens = len(st.session_state['sessao_vistoria'])
    st.progress(min(qtd_itens * 5, 100), text=f"Apontamentos na Sessão: {qtd_itens}")

    # NO MOBILE, USAMOS ABAS PARA ORGANIZAR EM VEZ DE COLUNAS APERTADAS
    tab_coleta, tab_revisao = st.tabs(["📸 Coleta de Dados", "📄 Revisar & Baixar"])

    with tab_coleta:
        with st.container(border=True):
            contexto_atual = CONTEXT_DATA[st.session_state['tipo_estabelecimento_atual']]
            lista_setores = contexto_atual["setores"]
            mapa_sugestoes = contexto_atual["sugestoes"]

            local = st.selectbox("1. Setor / Área", lista_setores)
            
            # --- SELEÇÃO POR CHECKBOX (MELHOR PARA MOBILE) ---
            sugestoes = mapa_sugestoes.get(local, mapa_sugestoes["DEFAULT"])
            
            selecionados_agora = []
            
            if sugestoes:
                st.info(f"👇 Toque para selecionar NCs em **{local}**:")
                with st.expander("🔍 Lista de Problemas Comuns (Toque aqui)", expanded=True):
                    for sug in sugestoes:
                        # Cria uma chave única para cada checkbox baseada no setor e texto
                        chave_chk = f"{local}_{sug}"
                        # Se marcado, adiciona à lista
                        if st.checkbox(sug, key=chave_chk):
                            selecionados_agora.append(sug)
            
            # Monta o texto automaticamente
            texto_automatico = ""
            if selecionados_agora:
                texto_automatico = " + ".join(selecionados_agora)
            
            st.markdown("---")
            st.write("2. Descrição da Não Conformidade")
            
            # Se tiver seleção automática, usa ela. Se o usuário editou manualmente antes, respeita a edição (complexo em stateless, vamos simplificar: o automático sobrescreve ou concatena)
            
            item_nome = st.text_area("Descrição Técnica", value=texto_automatico, height=150, help="O texto aqui será salvo no relatório. Você pode editar.")
            
            c1, c2 = st.columns(2)
            situacao = c1.radio("Status", ["❌ Não Conforme", "⚠️ Parcial", "✅ Conforme"], horizontal=False)
            gravidade = c2.select_slider("Risco", options=["Baixo", "Médio", "Alto", "CRÍTICO"], value="Alto")
            
            st.markdown("---")
            st.write("3. Evidências (Voz e Foto)")
            
            audio_input = st.audio_input("🎙️ Gravar Nota", key="mic_input")
            if audio_input and TEM_RECONHECIMENTO_VOZ:
                txt = transcrever_audio(audio_input)
                if txt and txt not in st.session_state['obs_atual']:
                    st.session_state['obs_atual'] += " " + txt
            
            obs = st.text_area("Detalhes Adicionais", value=st.session_state['obs_atual'], height=100, placeholder="Ex: Piso quebrado próximo à porta...")
            if obs != st.session_state['obs_atual']: st.session_state['obs_atual'] = obs

            foto_input = st.camera_input("📸 Capturar Foto")
            if foto_input:
                if not st.session_state['fotos_temp'] or foto_input.getvalue() != st.session_state['fotos_temp'][-1]:
                    st.session_state['fotos_temp'].append(foto_input.getvalue())
            
            if st.session_state['fotos_temp']:
                st.image([x for x in st.session_state['fotos_temp']], width=100, caption=[f"Foto {i+1}" for i in range(len(st.session_state['fotos_temp']))])
                if st.button("Limpar Fotos", type="secondary", use_container_width=True): 
                    st.session_state['fotos_temp'] = []; st.rerun()

            st.markdown("---")
            if st.button("💾 SALVAR APONTAMENTO", type="primary", use_container_width=True):
                if not item_nome: st.error("Descrição obrigatória.")
                else:
                    audio_blob = audio_input.getvalue() if audio_input else None
                    novo = {
                        "Local": local, "Item": item_nome, "Situação": situacao, "Gravidade": gravidade,
                        "Obs": st.session_state['obs_atual'], "Fotos": st.session_state['fotos_temp'].copy(),
                        "Audio_Bytes": audio_blob, "Hora": datetime.now().strftime("%H:%M")
                    }
                    st.session_state['sessao_vistoria'].append(novo)
                    # Limpeza pós-salvamento
                    st.session_state['fotos_temp'] = []
                    st.session_state['obs_atual'] = ""
                    # Reset checkboxes (gambiarra do streamlit: para resetar, precisamos dar rerun ou limpar session keys)
                    # Vamos manter simples: o usuario desmarca manual ou segue pro proximo setor
                    st.toast("Salvo com sucesso!", icon="✅")
                    time.sleep(0.5); st.rerun()

    with tab_revisao:
        st.subheader("📦 Itens Coletados")
        if not st.session_state['sessao_vistoria']:
            st.info("Nenhum apontamento ainda.")
        else:
            for i, reg in enumerate(st.session_state['sessao_vistoria']):
                # Card Visual para Mobile
                with st.container(border=True):
                    c_a, c_b = st.columns([4, 1])
                    c_a.markdown(f"**{i+1}. {reg['Local']}**")
                    c_a.caption(f"{reg['Item'][:100]}...") # Texto curto
                    if c_b.button("🗑️", key=f"del_{i}"):
                        st.session_state['sessao_vistoria'].pop(i); st.rerun()
            
            st.markdown("---")
            zip_data = gerar_pacote_zip_completo(st.session_state['sessao_vistoria'], st.session_state['tipo_estabelecimento_atual'])
            nome_zip = f"Relatorio_Legalizacao_{limpar_texto_pdf(st.session_state['tipo_estabelecimento_atual'])}_{datetime.now().strftime('%d-%m-%H%M')}.zip"
            
            st.download_button(
                label="📥 BAIXAR RELATÓRIO FINAL (ZIP)",
                data=zip_data,
                file_name=nome_zip,
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
            
            if st.button("Limpar Tudo e Começar Novo", type="secondary", use_container_width=True):
                st.session_state['sessao_vistoria'] = []
                st.rerun()

elif menu == "Relatórios":
    st.title("Histórico de Relatórios")
    st.info("Aqui você pode consultar relatórios antigos salvos no Banco de Dados.")
