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
    page_title="Legaliza Health", 
    page_icon="🏥", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS PREMIUM (DESIGN TECH) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Fundo Geral Escuro e Moderno */
    .stApp { 
        background-color: #111827; 
        color: #f3f4f6; 
    }
    
    /* Cards com efeito Glassmorphism */
    div[data-testid="metric-container"] {
        background: rgba(31, 41, 55, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-left: 4px solid #10b981; /* Verde Tech */
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(10px);
    }
    
    /* Botões Primários (Gradiente Tech) */
    div.stButton > button:first-child {
        border-radius: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        height: 50px;
        width: 100%;
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        border: none;
        color: white;
        box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.5);
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.6);
    }

    /* Tabelas Modernas */
    [data-testid="stDataFrame"] { 
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #374151;
    }

    /* Título do Menu Centralizado */
    .sidebar-title {
        text-align: center;
        font-size: 22px;
        font-weight: 800;
        color: #10b981; /* Verde Tech */
        margin-top: 20px;
        margin-bottom: 20px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        text-shadow: 0 0 10px rgba(16, 185, 129, 0.3);
    }

    /* Inputs e Selectbox */
    .stTextInput > div > div > input, .stSelectbox > div > div > div {
        border-radius: 10px;
        border: 1px solid #374151;
        background-color: #1f2937;
        color: white;
        height: 45px;
    }
</style>
""", unsafe_allow_html=True)

TOPICO_NOTIFICACAO = "legaliza_vida_alerta_hospital"
INTERVALO_CHECK_ROBO = 60
ID_PASTA_DRIVE = "1tGVSqvuy6D_FFz6nES90zYRKd0Tmd2wQ"

# --- 2. CÉREBRO DE INTELIGÊNCIA DINÂMICA ---
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
            "Linha de Produção": ["Máquinas sem proteção (NR-12)", "Área de circulação obstruída", "Painel elétrico sem tranca (NR-10)", "Iluminação insuficiente"],
            "Estoque/Almoxarifado": ["Empilhamento excessivo", "Extintores obstruídos", "Porta-pallets danificada", "Ausência de rota de fuga"],
            "DEFAULT": ["AVCB vencido", "Ausência de SPDA", "Descarte de efluentes irregular"]
        }
    },
    "🛒 Varejo de Alimentos": {
        "setores": ["Área de Venda", "Cozinha/Manipulação", "Estoque Seco", "Câmara Fria", "Saneantes", "Lixo"],
        "sugestoes": {
            "Cozinha/Manipulação": ["Fluxo cruzado", "Ausência de pia exclusiva mãos", "Ausência de tela milimétrica", "Luminárias sem proteção"],
            "Câmara Fria": ["Temperatura alta", "Gelo acumulado", "Alimentos no chão", "Porta não veda"],
            "DEFAULT": ["Licença Sanitária vencida", "Manual de Boas Práticas desatualizado", "Caixa d'Água suja"]
        }
    }
}

# --- 2.1 BASE DE DOCUMENTOS ---
DOC_INTELLIGENCE = {
    "Alvará de Funcionamento": {"dias": 365, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+alvara+funcionamento", "tarefas": ["Renovação", "Taxa"]},
    "Licença Sanitária": {"dias": 365, "risco": "CRÍTICO", "link": "https://www.google.com/search?q=consulta+licenca+sanitaria", "tarefas": ["Protocolo VISA", "Manual Boas Práticas"]},
    "DEFAULT": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Verificar validade"]}
}
# ADICIONANDO A BASE DE CONHECIMENTO COMPLETA
DOC_INTELLIGENCE.update({
    "Licença de Publicidade": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Medir fachada", "Pagar taxa TFA/Cadan", "Verificar padrão visual"]},
    "Inscrição Municipal": {"dias": 0, "risco": "NORMAL", "link": "", "tarefas": ["Verificar cadastro mobiliário", "Atualizar dados fiscais"]},
    "Habite-se": {"dias": 0, "risco": "CRÍTICO", "link": "", "tarefas": ["Verificar metragem construída", "Arquivar planta aprovada"]},
    "Alvará de Obra": {"dias": 180, "risco": "ALTO", "link": "", "tarefas": ["Placa do engenheiro na obra", "ART de execução", "Manter no canteiro"]},
    "Projeto Arquitetonico (Visa e Prefeitura)": {"dias": 0, "risco": "ALTO", "link": "", "tarefas": ["Aprovação LTA (Vigilância)", "Aprovação Prefeitura", "Memorial descritivo atualizado"]},
    "SDR": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Regularidade regional", "Taxas estaduais"]},
    "SMOP": {"dias": 365, "risco": "NORMAL", "link": "", "tarefas": ["Regularidade de obras viárias", "Certificado de conclusão"]},
    "Termo de aceite de sinalização de vaga para deficiente e idoso": {"dias": 0, "risco": "BAIXO", "link": "", "tarefas": ["Pintura de solo", "Placa vertical", "Medidas ABNT"]},
    "Certificado de acessibilidade": {"dias": 0, "risco": "MÉDIO", "link": "", "tarefas": ["Laudo NBR 9050", "Rampas/Banheiros adaptados"]},
    "Carta de anuência tombamento": {"dias": 0, "risco": "MÉDIO", "link": "", "tarefas": ["Verificar restrições de fachada", "Patrimônio histórico"]},
    "Certificado de Manutenção do Sistema de Segurança": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Laudo câmeras/CFTV", "Teste alarme", "Manutenção cercas"]},
    "Licença do Comando da Aeronáutica (COMAER)": {"dias": 1095, "risco": "ALTO", "link": "", "tarefas": ["Aprovação AGA", "Luz piloto topo prédio"]},
    "Polícia Civil (Licença)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Relatório trimestral", "Taxa fiscalização", "Vistoria local"]},
    "Polícia Civil (Termo de Vistoria)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Livro de registro", "Agendamento vistoria"]},
    "Polícia Federal (Licença)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Mapas mensais (químicos)", "Renovação CRC/CLF", "Controle estoque"]},
    "Licença Ambiental": {"dias": 1460, "risco": "MÉDIO", "link": "", "tarefas": ["Manifesto resíduos (MTR)", "PGRSS atualizado", "Renovação LO"]},
    "Cadastro de tanques, bombas e equipamentos afins": {"dias": 1825, "risco": "ALTO", "link": "", "tarefas": ["Teste estanqueidade", "Limpeza tanques", "Licença ambiental"]},
    "Conselho de Medicina (CRM)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Certificado Regularidade", "Lista corpo clínico", "Anuidade PJ", "Diretor Técnico"]},
    "Conselho de Enfermagem (COREN)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["CRT (Certidão Resp. Técnica)", "Dimensionamento equipe", "Escalas assinadas"]},
    "Conselho de Farmácia (CRF)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Certidão Regularidade", "Farmacêutico presente", "Baixa RT anterior"]},
    "Conselho de Odontologia (CRO)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Inscrição EPAO", "Dentista RT"]},
    "Conselho de Biomedicina (CRBM)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Registro PJ", "Biomédico RT"]},
    "Conselho de Biologia (CRBio)": {"dias": 365, "risco": "MÉDIO", "link": "", "tarefas": ["Registro PJ", "TRT emitido"]},
    "Conselho de Nutrição (CRN)": {"dias": 365, "risco": "MÉDIO", "link": "", "tarefas": ["CRQ (Quadro Técnico)", "Manual Boas Práticas"]},
    "Conselho de Psicologia (CRP)": {"dias": 365, "risco": "MÉDIO", "link": "", "tarefas": ["Cadastro PJ", "Psicólogo RT"]},
    "Conselho de Radiologia (CRTR)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Supervisor Proteção Radiológica", "Lista técnicos"]},
    "Conselho de Fisioterapia e Terapia Ocupacional (CREFITO)": {"dias": 365, "risco": "MÉDIO", "link": "", "tarefas": ["DRF (Declaração Regularidade)", "Fisioterapeuta RT"]},
    "Conselho de Fonoaudiologia (CREFONO)": {"dias": 365, "risco": "MÉDIO", "link": "", "tarefas": ["Registro PJ", "Fonoaudiólogo RT"]},
    "CNES": {"dias": 180, "risco": "CRÍTICO", "link": "https://cnes.datasus.gov.br/", "tarefas": ["Atualizar RT", "Atualizar quadro RH", "Atualizar equipamentos"]},
    "Licença Sanitária Serviço (Laboratório)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Controle Qualidade", "Pop's analíticos", "Gerenciamento resíduos"]},
    "Conselho de Biomedicina (CRBM) Serviço - Laboratório": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["RT Biomédico", "PNCQ", "Calibração"]},
    "Licença Sanitária Serviço (Farmácia)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Controle temperatura/umidade", "SNGPC (Controlados)", "Qualificação fornecedor"]},
    "Licença Sanitária Serviço (Radiologia)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Levantamento Radiométrico", "Testes Constância", "Dosimetria"]},
    "Licença Sanitária Serviço (Tomografia)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Programa Garantia Qualidade", "Testes aceitação", "Laudo físico"]},
    "Licença Sanitária Serviço (Hemoterapia)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Validação Rede Frio", "Ciclo do sangue", "Comitê Transfusional"]},
    "Licença Sanitária Serviço (Hemodiálise)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Análise água", "Manutenção máquinas", "Sorologia pacientes"]},
    "Licença Sanitária Serviço (Oncologia)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Protocolos quimioterapia", "Registro câncer"]},
    "Licença Sanitária Serviço (UTI Adulto)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Monitoramento 24h", "Equipamentos suporte", "CCIH"]},
    "Licença Sanitária Serviço (UTI Neonatal)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Incubadoras", "Rede gases", "Área ordenha"]},
    "Licença Sanitária Serviço (CME)": {"dias": 365, "risco": "CRÍTICO", "link": "", "tarefas": ["Testes autoclave", "Qualificação térmica", "Rastreabilidade"]},
    "Licença Sanitária Serviço (Vacinas)": {"dias": 365, "risco": "ALTO", "link": "", "tarefas": ["Rede de frio", "Gerador/Nobreak", "Registro doses"]},
    "Licença Sanitária Serviço (Equipamento)": {"dias": 365, "risco": "MÉDIO", "link": "", "tarefas": ["Plano Manutenção", "Calibração", "Teste Segurança Elétrica", "Etiqueta Validade"]},
})
for i in range(1, 23):
    DOC_INTELLIGENCE[f"Licença Sanitária Serviço (Equipamento {i})"] = DOC_INTELLIGENCE["Licença Sanitária Serviço (Equipamento)"]

LISTA_TIPOS_DOCUMENTOS = sorted(list(DOC_INTELLIGENCE.keys()) + ["Outros"])

# --- AUTO-REFRESH ---
components.html("""
<script>
    setTimeout(function(){
        window.location.reload(1);
    }, 600000); 
</script>
""", height=0)

# --- FUNÇÕES BÁSICAS ---
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

# --- LIMPEZA DE TEXTO CORRIGIDA (REMOVE EMOJIS DO TÍTULO) ---
def limpar_texto_pdf(texto):
    if texto is None: return ""
    texto = str(texto)
    # Remove emojis e caracteres especiais
    texto = texto.replace("✅", "[OK]").replace("❌", "[NC]").replace("⚠️", "[ATENCAO]")
    texto = texto.replace("🏥", "").replace("🏭", "").replace("🛒", "")
    texto = texto.replace("â", "a").replace("ã", "a").replace("á", "a").replace("ç", "c")
    texto = texto.replace("ê", "e").replace("é", "e").replace("í", "i").replace("ó", "o").replace("õ", "o").replace("ú", "u")
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

# --- FUNÇÕES DE CONEXÃO E DADOS ---
def get_creds():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

def conectar_gsheets():
    creds = get_creds()
    client = gspread.authorize(creds)
    return client.open("LegalizaHealth_DB")

@st.cache_data(ttl=60)
def carregar_tudo_inicial():
    try:
        sh = conectar_gsheets()
        ws_prazos = sh.worksheet("Prazos")
        df_prazos = pd.DataFrame(ws_prazos.get_all_records())
        try:
            ws_check = sh.worksheet("Checklist_Itens")
            df_check = pd.DataFrame(ws_check.get_all_records())
        except:
            ws_check = sh.add_worksheet("Checklist_Itens", 1000, 5)
            ws_check.append_row(["Documento_Ref", "Tarefa", "Feito"])
            df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])

        colunas = ["Unidade", "Setor", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido"]
        for c in colunas:
            if c not in df_prazos.columns: df_prazos[c] = ""
            
        if not df_prazos.empty:
            df_prazos["Progresso"] = pd.to_numeric(df_prazos["Progresso"], errors='coerce').fillna(0).astype(int)
            for col_txt in ['Unidade', 'Setor', 'Documento', 'Status', 'CNPJ']:
                df_prazos[col_txt] = df_prazos[col_txt].astype(str).str.strip()
            for c_date in ['Vencimento', 'Data_Recebimento']:
                df_prazos[c_date] = pd.to_datetime(df_prazos[c_date], dayfirst=True, errors='coerce').dt.date
            df_prazos = df_prazos[df_prazos['Unidade'] != ""]
            df_prazos['ID_UNICO'] = df_prazos['Unidade'] + " - " + df_prazos['Documento']
        
        if df_check.empty: df_check = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])
        else:
            df_check['Documento_Ref'] = df_check['Documento_Ref'].astype(str)
            df_check = df_check[df_check['Tarefa'] != ""]
        return df_prazos, df_check
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

def get_dados():
    if 'dados_cache' not in st.session_state or st.session_state['dados_cache'] is None:
        st.session_state['dados_cache'] = carregar_tudo_inicial()
    return st.session_state['dados_cache']

def update_dados_local(df_p, df_c):
    st.session_state['dados_cache'] = (df_p, df_c)

def salvar_alteracoes_completo(df_prazos, df_checklist):
    try:
        sh = conectar_gsheets()
        ws_prazos = sh.worksheet("Prazos")
        ws_prazos.clear()
        df_p = df_prazos.copy()
        if 'ID_UNICO' in df_p.columns: df_p = df_p.drop(columns=['ID_UNICO'])
        for c_date in ['Vencimento', 'Data_Recebimento']:
            df_p[c_date] = df_p[c_date].apply(lambda x: x.strftime('%d/%m/%Y') if hasattr(x, 'strftime') else str(x))
        df_p['Concluido'] = df_p['Concluido'].astype(str)
        df_p['Progresso'] = df_p['Progresso'].apply(safe_prog)
        colunas_ordem = ["Unidade", "Setor", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido"]
        for c in colunas_ordem: 
            if c not in df_p.columns: df_p[c] = ""
        df_p = df_p[colunas_ordem]
        ws_prazos.update([df_p.columns.values.tolist()] + df_p.values.tolist())
        
        ws_check = sh.worksheet("Checklist_Itens")
        ws_check.clear()
        df_c = df_checklist.copy()
        df_c['Feito'] = df_c['Feito'].astype(str)
        ws_check.update([df_c.columns.values.tolist()] + df_c.values.tolist())
        st.cache_data.clear()
        st.session_state['dados_cache'] = (df_prazos, df_checklist)
        st.toast("✅ Salvo!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")
        return False

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

def gerar_pacote_zip_completo(itens_vistoria, tipo_estabelecimento, nome_cliente, endereco_cliente):
    pdf = RelatorioPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    epw = pdf.w - 2*pdf.l_margin 
    
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(epw, 10, "DADOS DO CLIENTE / UNIDADE", 1, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(epw, 6, f"Cliente: {limpar_texto_pdf(nome_cliente)}\nEndereco: {limpar_texto_pdf(endereco_cliente)}\nTipo: {limpar_texto_pdf(tipo_estabelecimento)}", 1)
    pdf.ln(5)

    total = len(itens_vistoria)
    criticos = sum(1 for i in itens_vistoria if i['Gravidade'] == 'CRÍTICO')
    pdf.set_font("Arial", "B", 12)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(epw, 10, "RESUMO EXECUTIVO", 1, 1, 'L', fill=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(epw, 8, f"Total de Apontamentos: {total} | Pontos Criticos: {criticos}", 1, 1)
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
        pdf.multi_cell(epw, 8, f"#{idx+1} - {local_safe}", 1, 'L', fill=True)
        pdf.set_font("Arial", "B", 10)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(epw, 6, f"NC Identificada: {item_safe}", 1, 'L')
        pdf.set_font("Arial", "", 10)
        pdf.set_x(pdf.l_margin) 
        pdf.cell(epw/2, 6, f"Status: {limpar_texto_pdf(item['Situação'])}", 1, 0, 'L')
        pdf.cell(epw/2, 6, f"Risco: {limpar_texto_pdf(item['Gravidade'])}", 1, 1, 'L')
        info_extra = ""
        if item.get('Audio_Bytes'):
            nome_audio = f"Audio_Item_{idx+1}.wav"
            audios_para_zip.append((nome_audio, item['Audio_Bytes']))
            info_extra = f" [AUDIO ANEXO: {nome_audio}]"
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(epw, 6, f"Nota Tecnica: {obs_safe}{info_extra}", 1, 'L')
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
        else: pdf.ln(2)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(5)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        pdf_bytes = pdf.output() 
        zip_file.writestr(f"Relatorio_Vistoria_{datetime.now().strftime('%d-%m')}.pdf", pdf_bytes)
        for nome_arq, dados_audio in audios_para_zip:
            if hasattr(dados_audio, 'getvalue'): zip_file.writestr(nome_arq, dados_audio.getvalue())
            else: zip_file.writestr(nome_arq, dados_audio)
    return zip_buffer.getvalue()

# --- INTERFACE ---
if 'vistorias' not in st.session_state: st.session_state['vistorias'] = []
if 'sessao_vistoria' not in st.session_state: st.session_state['sessao_vistoria'] = []
if 'fotos_temp' not in st.session_state: st.session_state['fotos_temp'] = []
if 'obs_atual' not in st.session_state: st.session_state['obs_atual'] = ""
if 'tipo_estabelecimento_atual' not in st.session_state: st.session_state['tipo_estabelecimento_atual'] = "🏥 Hospital / Clínica / Laboratório"
if 'checks_temp' not in st.session_state: st.session_state['checks_temp'] = {}
if 'last_notify_critico' not in st.session_state: st.session_state['last_notify_critico'] = datetime.min
if 'last_notify_alto' not in st.session_state: st.session_state['last_notify_alto'] = datetime.min
if 'doc_focado_id' not in st.session_state: st.session_state['doc_focado_id'] = None
if 'filtro_dash' not in st.session_state: st.session_state['filtro_dash'] = "TODOS"
if 'cliente_nome' not in st.session_state: st.session_state['cliente_nome'] = ""
if 'cliente_endereco' not in st.session_state: st.session_state['cliente_endereco'] = ""

with st.sidebar:
    if img_loading: st.markdown(f"""<div style="text-align: center;"><img src="data:image/gif;base64,{img_loading}" width="100%" style="border-radius:10px;"></div>""", unsafe_allow_html=True)
    
    # TÍTULO CENTRALIZADO NO MENU
    st.markdown("<h1 class='sidebar-title'>Legaliza Health</h1>", unsafe_allow_html=True)
    
    # MENU SEM A OPÇÃO RELATÓRIOS
    menu = option_menu(
        menu_title=None, 
        options=["Painel Geral", "Gestão de Docs", "Vistoria Mobile"], 
        icons=["speedometer2", "folder-check", "camera-fill"], 
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#00c853", "font-size": "18px"},
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"5px", "--hover-color": "#262730"},
            "nav-link-selected": {"background-color": "#1f2937"},
        }
    )
    st.caption("v65.0 - Redesign Final")

# --- ROBÔ ---
try:
    agora = datetime.now()
    diff_crit = (agora - st.session_state['last_notify_critico']).total_seconds() / 60
    diff_alto = (agora - st.session_state['last_notify_alto']).total_seconds() / 60
    df_alertas = get_dados()[0]
    if df_alertas is not None:
        msgs_crit = []
        msgs_alto = []
        hoje = datetime.now(pytz.timezone('America/Sao_Paulo')).date()
        for index, row in df_alertas.iterrows():
            try:
                doc_nome = str(row['Documento'])
                if "SELECIONE" in doc_nome or "PENDENTE" in doc_nome: continue
                if row['Status'] == "NORMAL": continue
                prog = safe_prog(row['Progresso'])
                if prog >= 100: continue
                dias = (row['Vencimento'] - hoje).days
                unidade = row['Unidade']
                risco = row['Status']
                msg = f"🏥 {unidade}\n📄 {doc_nome}\n⏳ Vence em {dias} dias"
                if risco == "CRÍTICO" and (dias <= 5 or dias < 0): msgs_crit.append(msg)
                elif risco == "ALTO" and (dias <= 5 or dias < 0): msgs_alto.append(msg)
            except: pass
        if msgs_crit and diff_crit >= 60:
            corpo = "\n----------------\n".join(msgs_crit[:10])
            if enviar_notificacao_push("🚨 ALERTA CRÍTICO (1h)", corpo, "high"): st.session_state['last_notify_critico'] = agora
        if msgs_alto and diff_alto >= 180:
            corpo = "\n----------------\n".join(msgs_alto[:10])
            if enviar_notificacao_push("🟠 ALERTA ALTO (3h)", corpo, "default"): st.session_state['last_notify_alto'] = agora
except Exception as e: pass

# --- TELAS ---
if menu == "Painel Geral":
    st.title("Painel Estratégico")
    df_p, _ = get_dados()
    if df_p.empty:
        st.warning("Ainda não há documentos cadastrados. Adicione na aba 'Gestão de Docs'.")
        st.stop()
    n_crit = len(df_p[df_p['Status'] == "CRÍTICO"])
    n_alto = len(df_p[df_p['Status'] == "ALTO"])
    n_norm = len(df_p[df_p['Status'] == "NORMAL"])
    c1, c2, c3, c4 = st.columns(4)
    if c1.button(f"🔴 CRÍTICO: {n_crit}", use_container_width=True): st.session_state['filtro_dash'] = "CRÍTICO"
    if c2.button(f"🟠 ALTO: {n_alto}", use_container_width=True): st.session_state['filtro_dash'] = "ALTO"
    if c3.button(f"🟢 NORMAL: {n_norm}", use_container_width=True): st.session_state['filtro_dash'] = "NORMAL"
    if c4.button(f"📋 TOTAL: {len(df_p)}", use_container_width=True): st.session_state['filtro_dash'] = "TODOS"
    st.markdown("---")
    busca_painel = st.text_input("🔎 Buscar Unidade/Documento", placeholder="Ex: gravatai, crm, alvara...")
    f_atual = st.session_state['filtro_dash']
    st.subheader(f"Lista de Processos: {f_atual}")
    df_show = df_p.copy()
    if f_atual != "TODOS": df_show = df_show[df_show['Status'] == f_atual]
    if busca_painel:
        termo = normalizar_texto(busca_painel)
        df_show = df_show[df_show.apply(lambda row: termo in normalizar_texto(str(row.values)), axis=1)]
    if not df_show.empty:
        st.dataframe(df_show[['Unidade', 'Setor', 'Documento', 'Vencimento', 'Progresso', 'Status']], use_container_width=True, hide_index=True, column_config={"Vencimento": st.column_config.DateColumn("Prazo", format="DD/MM/YYYY"), "Progresso": st.column_config.ProgressColumn("Progressão", format="%d%%"), "Status": st.column_config.TextColumn("Risco", width="small")})
    else: st.info("Nenhum item encontrado.")
    st.markdown("---")
    st.subheader("Panorama")
    if not df_p.empty and TEM_PLOTLY:
        status_counts = df_p['Status'].value_counts()
        fig = px.pie(values=status_counts.values, names=status_counts.index, hole=0.6, color=status_counts.index, color_discrete_map={"CRÍTICO": "#ff4b4b", "ALTO": "#ffa726", "NORMAL": "#00c853"})
        fig.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)
        media = int(df_p['Progresso'].mean()) if not df_p.empty else 0
        st.metric("Progressão Geral", f"{media}%")
        st.progress(media)

elif menu == "Gestão de Docs":
    st.title("Gestão de Documentos")
    df_prazos, df_checklist = get_dados()
    with st.expander("🔍 FILTROS", expanded=True):
        f1, f2, f3 = st.columns(3)
        lista_uni = ["Todas"] + sorted(list(df_prazos['Unidade'].unique())) if 'Unidade' in df_prazos.columns else ["Todas"]
        f_uni = f1.selectbox("Unidade:", lista_uni)
        f_stt = f2.multiselect("Status:", ["CRÍTICO", "ALTO", "NORMAL"])
        f_txt = f3.text_input("Buscar Inteligente (Nome/CNPJ/Setor):")
        if st.button("Limpar"): st.rerun()
    df_show = df_prazos.copy()
    if f_uni != "Todas": df_show = df_show[df_show['Unidade'] == f_uni]
    if f_stt: df_show = df_show[df_show['Status'].isin(f_stt)]
    if f_txt:
        termo = normalizar_texto(f_txt)
        df_show = df_show[df_show.apply(lambda row: termo in normalizar_texto(str(row.values)), axis=1)]
    col_l, col_d = st.columns([1.2, 2])
    with col_l:
        st.info(f"Lista ({len(df_show)})")
        sel = st.dataframe(df_show[['Unidade', 'Documento', 'Status']], use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", column_config={"Status": st.column_config.TextColumn("Risco", width="small")})
        if len(sel.selection.rows) > 0:
            idx_real = sel.selection.rows[0]
            doc_selecionado_id = df_show.iloc[idx_real]['ID_UNICO']
            st.session_state['doc_focado_id'] = doc_selecionado_id
        doc_ativo_id = st.session_state.get('doc_focado_id')
        st.markdown("---")
        with st.expander("➕ Novo Documento (Manual)"):
            with st.form("new_doc", clear_on_submit=True):
                n_u = st.text_input("Unidade"); n_s = st.text_input("Setor"); n_d = st.selectbox("Documento", options=LISTA_TIPOS_DOCUMENTOS); n_c = st.text_input("CNPJ")
                if st.form_submit_button("ADICIONAR"):
                    if n_u and n_d and n_c:
                        risco_sug, venc_sug, link_sug, tarefas_sug = aplicar_inteligencia_doc(n_d)
                        novo = {"Unidade": n_u, "Setor": n_s, "Documento": n_d, "CNPJ": n_c, "Data_Recebimento": date.today(), "Vencimento": venc_sug, "Status": risco_sug, "Progresso": 0, "Concluido": "False"}
                        df_temp = pd.concat([pd.DataFrame([novo]), df_prazos], ignore_index=True)
                        df_temp['ID_UNICO'] = df_temp['Unidade'] + " - " + df_temp['Documento']
                        if tarefas_sug: df_checklist = adicionar_tarefas_sugeridas(df_checklist, df_temp['ID_UNICO'].iloc[0], tarefas_sug)
                        update_dados_local(df_temp, df_checklist)
                        st.toast(f"Criado! Checklist sugerido carregado.", icon="✅")
                        st.rerun()
                    else: st.error("Preencha Unidade, Documento e CNPJ.")
        st.markdown("---")
        with st.expander("⬆️ Importar Unidades/CNPJ (Excel/CSV)"):
            import_file = st.file_uploader("Carregar arquivo (.xlsx ou .csv)", type=['xlsx', 'csv'], key="uploader_import_mass")
            if import_file:
                df_novo = pd.DataFrame()
                try:
                    try: df_novo = pd.read_excel(import_file)
                    except:
                        import_file.seek(0)
                        try: df_novo = pd.read_csv(import_file, sep=';', encoding='latin-1')
                        except: 
                            import_file.seek(0)
                            df_novo = pd.read_csv(import_file, sep=',', encoding='utf-8')
                    if not df_novo.empty:
                        df_novo.columns = df_novo.columns.str.strip()
                        if 'Nome da unidade' in df_novo.columns and 'CNPJ' in df_novo.columns:
                            df_import = df_novo[['Nome da unidade', 'CNPJ']].copy()
                            df_import = df_import.rename(columns={'Nome da unidade': 'Unidade'})
                            st.write("### 🔎 Pré-visualização:")
                            st.dataframe(df_import.head(5), use_container_width=True)
                            if st.button(f"✅ Confirmar Importação", type="primary"):
                                df_import['Setor'] = ""
                                df_import['Documento'] = "⚠️ SELECIONE O TIPO"
                                df_import['Data_Recebimento'] = date.today()
                                df_import['Vencimento'] = date.today()
                                df_import['Status'] = "NORMAL"
                                df_import['Progresso'] = 0
                                df_import['Concluido'] = "False"
                                df_import['Unidade'] = df_import['Unidade'].astype(str)
                                df_import['CNPJ'] = df_import['CNPJ'].astype(str)
                                df_import['ID_UNICO'] = df_import['Unidade'] + " - " + df_import['CNPJ'] + " - " + df_import['Documento']
                                df_combinado = pd.concat([df_prazos, df_import], ignore_index=True)
                                df_combinado = df_combinado.drop_duplicates(subset=['ID_UNICO'], keep='last').reset_index(drop=True)
                                salvar_alteracoes_completo(df_combinado, df_checklist)
                                st.success(f"✅ {len(df_import)} importados!")
                                st.balloons()
                                time.sleep(1)
                                st.rerun()
                        else: st.error(f"Necessário colunas 'Nome da unidade' e 'CNPJ'.")
                except Exception as e: st.error(f"Erro: {e}")
        st.markdown("---")
        with st.expander("🗑️ ZONA DE PERIGO (Excluir Tudo)"):
            st.warning("Atenção: Isso apagará TODOS os documentos e tarefas.")
            confirm = st.checkbox("Sim, quero excluir tudo")
            if confirm:
                if st.button("❌ EXCLUIR TODA A LISTA", type="primary"):
                    df_prazos = pd.DataFrame(columns=["Unidade", "Setor", "Documento", "CNPJ", "Data_Recebimento", "Vencimento", "Status", "Progresso", "Concluido", "ID_UNICO"])
                    df_checklist = pd.DataFrame(columns=["Documento_Ref", "Tarefa", "Feito"])
                    salvar_alteracoes_completo(df_prazos, df_checklist)
                    st.session_state['doc_focado_id'] = None
                    st.success("Tudo excluído!")
                    time.sleep(1)
                    st.rerun()
    with col_d:
        if doc_ativo_id:
            indices = df_prazos[df_prazos['ID_UNICO'] == doc_ativo_id].index
            if not indices.empty:
                idx = indices[0]
                doc_nome = df_prazos.at[idx, 'Documento']
                c_tit, c_edit_btn = st.columns([3, 1.5], vertical_alignment="bottom")
                opcoes_docs = LISTA_TIPOS_DOCUMENTOS.copy()
                if doc_nome not in opcoes_docs: opcoes_docs.insert(0, doc_nome) 
                try: idx_atual = opcoes_docs.index(doc_nome)
                except: idx_atual = 0
                novo_nome_doc = c_tit.selectbox("Tipo de Documento", options=opcoes_docs, index=idx_atual, key=f"nome_doc_{doc_ativo_id}")
                _, _, link_inteligente, tarefas_inteligentes = aplicar_inteligencia_doc(novo_nome_doc)
                if novo_nome_doc != doc_nome:
                     if c_edit_btn.button("Salvar Tipo"):
                        antigo_id = doc_ativo_id
                        nova_unidade = df_prazos.at[idx, 'Unidade']
                        cnpj_atual = df_prazos.at[idx, 'CNPJ']
                        risco_sug, venc_sug, _, _ = aplicar_inteligencia_doc(novo_nome_doc, df_prazos.at[idx, 'Data_Recebimento'])
                        df_prazos.at[idx, 'Status'] = risco_sug
                        df_prazos.at[idx, 'Vencimento'] = venc_sug
                        novo_id = nova_unidade + " - " + cnpj_atual + " - " + novo_nome_doc
                        df_prazos.at[idx, 'Documento'] = novo_nome_doc
                        df_prazos.at[idx, 'ID_UNICO'] = novo_id
                        df_checklist.loc[df_checklist['Documento_Ref'] == antigo_id, 'Documento_Ref'] = novo_id
                        update_dados_local(df_prazos, df_checklist)
                        st.session_state['doc_focado_id'] = novo_id
                        st.toast(f"Atualizado! Risco sugerido: {risco_sug}", icon="🧠")
                        st.rerun()
                st.caption(f"Unidade: {df_prazos.at[idx, 'Unidade']} | Setor: {df_prazos.at[idx, 'Setor']} | CNPJ: {df_prazos.at[idx, 'CNPJ']}")
                if link_inteligente: st.link_button(f"🌎 Pesquisar {novo_nome_doc}", link_inteligente)
                c_del, _ = st.columns([1, 4])
                if c_del.button("🗑️ Excluir"):
                    df_prazos = df_prazos.drop(idx).reset_index(drop=True)
                    df_checklist = df_checklist[df_checklist['Documento_Ref'] != doc_ativo_id]
                    update_dados_local(df_prazos, df_checklist)
                    st.session_state['doc_focado_id'] = None
                    st.rerun()
                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    st_curr = df_prazos.at[idx, 'Status']
                    opcoes = ["NORMAL", "ALTO", "CRÍTICO"]
                    if st_curr not in opcoes: st_curr = "NORMAL"
                    novo_risco = c1.selectbox("Risco", opcoes, index=opcoes.index(st_curr), key=f"sel_r_{doc_ativo_id}")
                    if novo_risco != st_curr:
                         df_prazos.at[idx, 'Status'] = novo_risco
                         update_dados_local(df_prazos, df_checklist)
                    cor_badge = "#ff4b4b" if st_curr == "CRÍTICO" else "#ffa726" if st_curr == "ALTO" else "#00c853"
                    c1.markdown(f'<span style="background-color:{cor_badge}; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; color: white;">Status: {st_curr}</span>', unsafe_allow_html=True)
                    novo_setor = st.text_input("Editar Setor", value=df_prazos.at[idx, 'Setor'], key=f"edit_sector_{doc_ativo_id}")
                    if novo_setor != df_prazos.at[idx, 'Setor']:
                        df_prazos.at[idx, 'Setor'] = novo_setor
                        update_dados_local(df_prazos, df_checklist)
                    try: d_rec = pd.to_datetime(df_prazos.at[idx, 'Data_Recebimento'], dayfirst=True).date()
                    except: d_rec = date.today()
                    nova_d_rec = c2.date_input("Recebido", value=d_rec, format="DD/MM/YYYY", key=f"dt_rec_{doc_ativo_id}")
                    if nova_d_rec != d_rec:
                        df_prazos.at[idx, 'Data_Recebimento'] = nova_d_rec
                        update_dados_local(df_prazos, df_checklist)
                    try: d_venc = pd.to_datetime(df_prazos.at[idx, 'Vencimento'], dayfirst=True).date()
                    except: d_venc = date.today()
                    nova_d_venc = c3.date_input("Vence", value=d_venc, format="DD/MM/YYYY", key=f"dt_venc_{doc_ativo_id}")
                    if nova_d_venc != d_venc:
                        df_prazos.at[idx, 'Vencimento'] = nova_d_venc
                        update_dados_local(df_prazos, df_checklist)
                    prog_atual = safe_prog(df_prazos.at[idx, 'Progresso'])
                    prog_bar_placeholder = st.empty()
                    prog_bar_placeholder.progress(prog_atual, text=f"Progressão: {prog_atual}%")
                st.write("✅ **Tarefas (Edição Rápida)**")
                df_checklist['Feito'] = df_checklist['Feito'].replace({'TRUE': True, 'FALSE': False, 'True': True, 'False': False, 'nan': False})
                df_checklist['Feito'] = df_checklist['Feito'].fillna(False).astype(bool)
                df_checklist['Documento_Ref'] = df_checklist['Documento_Ref'].astype(str)
                mask = df_checklist['Documento_Ref'] == str(doc_ativo_id)
                df_t = df_checklist[mask].copy().reset_index(drop=True)
                tarefas_existentes = df_t['Tarefa'].tolist()
                ha_novas_sugestoes = any(t for t in tarefas_inteligentes if t not in tarefas_existentes)
                if ha_novas_sugestoes:
                    if st.button("📥 Carregar Checklist Sugerido", key=f"load_tasks_{doc_ativo_id}"):
                        df_checklist = adicionar_tarefas_sugeridas(df_checklist, doc_ativo_id, tarefas_inteligentes)
                        update_dados_local(df_prazos, df_checklist)
                        st.rerun()
                c_add, c_btn = st.columns([3, 1])
                new_t = c_add.text_input("Nova tarefa...", label_visibility="collapsed", key=f"new_t_{doc_ativo_id}")
                if c_btn.button("ADICIONAR", key=f"btn_add_{doc_ativo_id}"):
                    if new_t:
                        line = pd.DataFrame([{"Documento_Ref": doc_ativo_id, "Tarefa": new_t, "Feito": False}])
                        df_checklist = pd.concat([df_checklist, line], ignore_index=True)
                        update_dados_local(df_prazos, df_checklist)
                        st.rerun()
                if not df_t.empty:
                    edited = st.data_editor(df_t, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"Documento_Ref": None, "Tarefa": st.column_config.TextColumn("Descrição", width="medium"), "Feito": st.column_config.CheckboxColumn("OK", width="small")}, key=f"ed_{doc_ativo_id}")
                    tot = len(edited); done = edited['Feito'].sum(); new_p = int((done/tot)*100) if tot > 0 else 0
                    prog_bar_placeholder.progress(new_p, text=f"Progressão: {new_p}%")
                    if not edited.equals(df_t) or new_p != prog_atual:
                        df_prazos.at[idx, 'Progresso'] = new_p
                        df_checklist = df_checklist[~mask]
                        edited['Documento_Ref'] = str(doc_ativo_id)
                        df_checklist = pd.concat([df_checklist, edited], ignore_index=True)
                        update_dados_local(df_prazos, df_checklist)
                        st.rerun()
                else: st.info("Adicione tarefas acima.")
                st.markdown("---")
                if st.button("💾 SALVAR TUDO NA NUVEM", type="primary"):
                    if salvar_alteracoes_completo(df_prazos, df_checklist): time.sleep(0.5); st.rerun()
            else:
                st.warning("Documento não encontrado.")
                if st.button("Voltar"): st.session_state['doc_focado_id'] = None; st.rerun()
        else: st.info("👈 Selecione um documento na lista.")

elif menu == "Vistoria Mobile":
    st.title("📋 Vistoria Técnica")
    st.write("📍 **Cabeçalho do Relatório**")
    with st.container(border=True):
        c_cli, c_end = st.columns(2)
        cliente_val = st.session_state.get('cliente_nome', "")
        cliente = c_cli.text_input("Nome da Unidade/Cliente", value=cliente_val, placeholder="Ex: Hospital Santa Cruz")
        endereco_val = st.session_state.get('cliente_endereco', "")
        endereco = c_end.text_input("Cidade / Endereço", value=endereco_val, placeholder="Ex: São Paulo - SP")
        if cliente != st.session_state['cliente_nome']: st.session_state['cliente_nome'] = cliente
        if endereco != st.session_state['cliente_endereco']: st.session_state['cliente_endereco'] = endereco
    st.write("⚙️ **Contexto**")
    if st.session_state['tipo_estabelecimento_atual'] not in CONTEXT_DATA.keys():
        st.session_state['tipo_estabelecimento_atual'] = list(CONTEXT_DATA.keys())[0]
    tipo_estab = st.selectbox("Tipo de Estabelecimento", options=list(CONTEXT_DATA.keys()), index=list(CONTEXT_DATA.keys()).index(st.session_state['tipo_estabelecimento_atual']))
    if tipo_estab != st.session_state['tipo_estabelecimento_atual']:
        st.session_state['tipo_estabelecimento_atual'] = tipo_estab
        st.session_state['checks_temp'] = {} 
        st.rerun()
    st.markdown("---")
    qtd_itens = len(st.session_state['sessao_vistoria'])
    st.progress(min(qtd_itens * 5, 100), text=f"Apontamentos na Sessão: {qtd_itens}")
    tab_coleta, tab_revisao = st.tabs(["📸 Coleta de Dados", "📄 Revisar & Baixar"])
    with tab_coleta:
        with st.container(border=True):
            contexto_atual = CONTEXT_DATA[st.session_state['tipo_estabelecimento_atual']]
            lista_setores = contexto_atual["setores"]
            mapa_sugestoes = contexto_atual["sugestoes"]
            local = st.selectbox("1. Setor / Área", lista_setores)
            sugestoes = mapa_sugestoes.get(local, mapa_sugestoes["DEFAULT"])
            selecionados_agora = []
            if sugestoes:
                st.info(f"👇 Toque para selecionar NCs em **{local}**:")
                with st.expander("🔍 Lista de Problemas Comuns (Toque aqui)", expanded=True):
                    for sug in sugestoes:
                        chave_chk = f"{local}_{sug}"
                        if st.checkbox(sug, key=chave_chk):
                            selecionados_agora.append(sug)
            texto_automatico = ""
            if selecionados_agora:
                texto_automatico = " + ".join(selecionados_agora)
            st.markdown("---")
            st.write("2. Descrição da Não Conformidade")
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
                    novo = {"Local": local, "Item": item_nome, "Situação": situacao, "Gravidade": gravidade, "Obs": st.session_state['obs_atual'], "Fotos": st.session_state['fotos_temp'].copy(), "Audio_Bytes": audio_blob, "Hora": datetime.now().strftime("%H:%M")}
                    st.session_state['sessao_vistoria'].append(novo)
                    st.session_state['fotos_temp'] = []
                    st.session_state['obs_atual'] = ""
                    st.toast("Salvo com sucesso!", icon="✅")
                    time.sleep(0.5); st.rerun()
    with tab_revisao:
        st.subheader("📦 Itens Coletados")
        if not st.session_state['sessao_vistoria']: st.info("Nenhum apontamento ainda.")
        else:
            for i, reg in enumerate(st.session_state['sessao_vistoria']):
                with st.container(border=True):
                    c_a, c_b = st.columns([4, 1])
                    c_a.markdown(f"**{i+1}. {reg['Local']}**")
                    c_a.caption(f"{reg['Item'][:100]}...")
                    if c_b.button("🗑️", key=f"del_{i}"):
                        st.session_state['sessao_vistoria'].pop(i); st.rerun()
            st.markdown("---")
            zip_data = gerar_pacote_zip_completo(st.session_state['sessao_vistoria'], st.session_state['tipo_estabelecimento_atual'], st.session_state['cliente_nome'], st.session_state['cliente_endereco'])
            nome_zip = f"Relatorio_Legalizacao_{limpar_texto_pdf(st.session_state['tipo_estabelecimento_atual'])}_{datetime.now().strftime('%d-%m-%H%M')}.zip"
            st.download_button(label="📥 BAIXAR RELATÓRIO FINAL (ZIP)", data=zip_data, file_name=nome_zip, mime="application/zip", type="primary", use_container_width=True)
            if st.button("Limpar Tudo e Começar Novo", type="secondary", use_container_width=True):
                st.session_state['sessao_vistoria'] = []; st.rerun()
