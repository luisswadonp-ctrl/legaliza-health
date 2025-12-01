import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from fpdf import FPDF
import tempfile
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64

# --- 1. CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="LegalizaHealth Pro", page_icon="🏥", layout="wide")

# Função para carregar imagem (Suporta GIF agora)
def get_img_as_base64(file):
    try:
        with open(file, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""

# Tenta carregar o GIF
img_loading = get_img_as_base64("loading.gif") 

# CSS Profissional
st.markdown(f"""
<style>
    .stApp {{ background-color: #f8f9fa; }}
    /* (O resto do CSS continua igual...) */
""", unsafe_allow_html=True)
