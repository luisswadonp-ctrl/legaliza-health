import streamlit as st
import pandas as pd
from datetime import datetime, date

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LegalizaHealth", page_icon="🏥", layout="wide")

# --- 1. LÓGICA DE NEGÓCIO (CÉREBRO) ---

def calcular_status(data_vencimento_str):
    try:
        # Tenta converter formato brasileiro
        data_venc = datetime.strptime(data_vencimento_str, "%d/%m/%Y").date()
    except ValueError:
        try:
             # Tenta formato internacional (caso o excel salve assim)
             data_venc = datetime.strptime(data_vencimento_str, "%Y-%m-%d").date()
        except:
            return None, "Erro Data", "grey"

    hoje = date.today()
    dias_restantes = (data_venc - hoje).days

    if dias_restantes <= 3:
        return dias_restantes, "🔴 PRIORIDADE TOTAL", "#ff4d4d" # Vermelho
    elif dias_restantes <= 15:
        return dias_restantes, "🟠 Atenção (Alta)", "#ffa500" # Laranja
    else:
        return dias_restantes, "🟢 No Prazo", "#28a745" # Verde

# --- 2. SISTEMA DE DADOS (SIMULAÇÃO) ---
# Como estamos na web, usamos "Session State" para guardar dados enquanto a aba está aberta.
# Num futuro próximo, substituiremos isso por Google Sheets ou Banco de Dados.

if 'documentos' not in st.session_state:
    st.session_state['documentos'] = []

if 'vistorias' not in st.session_state:
    st.session_state['vistorias'] = []

# --- 3. INTERFACE (SIDEBAR - MENU LATERAL) ---
st.sidebar.title("🏥 Menu Principal")
menu = st.sidebar.radio("Navegar para:", ["Gestão de Prazos", "Nova Vistoria", "Relatórios"])

# --- PÁGINA 1: GESTÃO DE PRAZOS (O que já fizemos) ---
if menu == "Gestão de Prazos":
    st.title("📅 Gestão de Prazos Críticos")
    st.markdown("---")

    # Formulário na barra lateral ou no topo
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        novo_doc = st.text_input("Nome do Documento / Pendência")
    with col2:
        nova_data = st.text_input("Data (dd/mm/aaaa)")
    with col3:
        st.write("") # Espaço para alinhar o botão
        st.write("")
        btn_add = st.button("➕ Adicionar")

    if btn_add:
        if novo_doc and nova_data:
            dias, status, cor = calcular_status(nova_data)
            if dias is not None:
                # Adiciona na lista
                st.session_state['documentos'].append({
                    "Documento": novo_doc,
                    "Vencimento": nova_data,
                    "Dias Restantes": dias,
                    "Status": status,
                    "Cor": cor
                })
                st.success("Adicionado!")
            else:
                st.error("Data inválida. Use dia/mês/ano")
        else:
            st.warning("Preencha tudo.")

    # Exibição dos Dados (Estilo Tabela Excel)
    if len(st.session_state['documentos']) > 0:
        # Criamos um DataFrame (Tabela Inteligente)
        df = pd.DataFrame(st.session_state['documentos'])
        
        # Mostramos na tela cartões para os itens CRÍTICOS (Regra da Vida)
        criticos = df[df['Status'] == "🔴 PRIORIDADE TOTAL"]
        if not criticos.empty:
            st.error(f"🚨 ATENÇÃO: Existem {len(criticos)} itens com PRIORIDADE TOTAL!")
            for index, row in criticos.iterrows():
                st.toast(f"URGENTE: {row['Documento']} vence em {row['Dias Restantes']} dias!")

        # Mostra a tabela completa colorida
        st.subheader("Lista de Monitoramento")
        
        # Função para colorir a tabela visualmente
        def colorir_linhas(val):
            color = 'white'
            if val == "🔴 PRIORIDADE TOTAL": color = '#ffcccc'
            elif val == "🟠 Atenção (Alta)": color = '#fff4cc'
            elif val == "🟢 No Prazo": color = '#ccffcc'
            return f'background-color: {color}'

        # Mostra tabela (sem a coluna 'Cor' que é interna)
        st.dataframe(df[['Documento', 'Vencimento', 'Dias Restantes', 'Status']], use_container_width=True)
        
        if st.button("🗑️ Limpar Lista"):
            st.session_state['documentos'] = []
            st.rerun()

# --- PÁGINA 2: NOVA VISTORIA (NOVIDADE!) ---
elif menu == "Nova Vistoria":
    st.title("📸 Checklist de Auditoria")
    st.markdown("Use esta tela durante a caminhada no hospital.")
    
    with st.form("form_vistoria"):
        col_a, col_b = st.columns(2)
        
        with col_a:
            setor = st.selectbox("Setor / Sala", ["Recepção", "Raio-X", "UTI", "Expurgo", "Farmácia", "Cozinha"])
            item_avaliado = st.text_input("Item Avaliado", placeholder="Ex: Lixeira Infectante")
        
        with col_b:
            conformidade = st.radio("Situação", ["✅ Conforme", "❌ NÃO Conforme"])
            prioridade = st.select_slider("Gravidade", options=["Baixa", "Média", "Alta", "CRÍTICA"])

        obs = st.text_area("Observações / O que precisa ser feito?")
        
        # O PULO DO GATO: Tira foto na hora
        foto = st.camera_input("Tirar foto da evidência")
        
        enviar = st.form_submit_button("💾 Salvar Item da Vistoria")

        if enviar:
            dados_vistoria = {
                "Setor": setor,
                "Item": item_avaliado,
                "Situação": conformidade,
                "Gravidade": prioridade,
                "Obs": obs,
                "Foto": "Sim" if foto else "Não"
            }
            st.session_state['vistorias'].append(dados_vistoria)
            st.success("Item registrado no relatório!")

# --- PÁGINA 3: RELATÓRIOS ---
elif menu == "Relatórios":
    st.title("📊 Relatório Consolidado")
    
    if len(st.session_state['vistorias']) > 0:
        df_vistoria = pd.DataFrame(st.session_state['vistorias'])
        st.write("Itens vistoriados nesta sessão:")
        st.dataframe(df_vistoria, use_container_width=True)
        
        # Botão para baixar Excel (Simulando o relatório final)
        # O Streamlit converte o DataFrame para CSV nativamente
        csv = df_vistoria.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Baixar Relatório (Excel/CSV)",
            data=csv,
            file_name=f"relatorio_vistoria_{date.today()}.csv",
            mime="text/csv",
        )
    else:
        st.info("Nenhuma vistoria realizada ainda.")