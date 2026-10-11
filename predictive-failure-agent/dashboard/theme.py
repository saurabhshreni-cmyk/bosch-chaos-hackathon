"""Shared visual styling; never changes operation authorization."""
import streamlit as st


def apply_theme():
    st.markdown("""<style>
    .stApp { background: #fff; color: #142b4b; }
    .block-container { padding-top: 2rem; max-width: 1500px; }
    h1,h2,h3 { color: #10294c; letter-spacing: -.025em; }
    [data-testid="stSidebar"] { background: #eef3fa; border-right: 1px solid #dce5f0; }
    [data-testid="stMetric"] { background: #f5f8fc; border: 1px solid #dce5f0;
      border-top: 3px solid #173c70; padding: 20px; border-radius: 12px; }
    [data-testid="stMetricValue"] { color: #10294c; }
    .stButton > button { border-radius: 8px; border-color: #becde0; }
    .stButton > button:hover { border-color: #173c70; background: #eef3fa; }
    .stButton > button[kind="primary"] { background: #173c70; color: #fff; }
    [data-testid="stExpander"] { border: 1px solid #dce5f0; border-radius: 10px; }
    [data-baseweb="tab-list"] { border-bottom: 1px solid #dce5f0; gap: 12px; }
    [aria-selected="true"][role="tab"] { color: #173c70; font-weight: 700; }
    </style>""", unsafe_allow_html=True)
