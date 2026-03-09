from __future__ import annotations

import json
import os
from datetime import date

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from src.db import save_run, get_runs_for_user

from src.analysis import analysis_to_markdown, generate_analysis
from src.evaluation import EvalResult, run_evaluation
from src.orchestrator import RunConfig, RunOutput, run_pipeline
from src.scenarios import SCENARIOS

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Meeting Notes → Action Items",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────
with open('.streamlit/config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

def render_auth_screen():
    # Hide sidebar while logged out 
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] { display: none; }
            section[data-testid="stSidebar"] { display: none; }
            .auth-container {
                max-width: 400px;
                margin: auto;
                padding-top: 10vh;
            }
        </style>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        try:
            authenticator.login()
        except Exception as e:
            st.error(e)

    with tab2:
        try:
            try:
                email, username, name = authenticator.register_user(pre_authorization=False)
            except TypeError: # Handle different arg names between versions
                email, username, name = authenticator.register_user()

            if email:
                try:
                    with open('.streamlit/config.yaml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
                    st.success('User registered successfully. You can now login.')
                except Exception as e:
                    st.error(e)
        except Exception as e:
            st.error(e)

    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state.get("authentication_status"):
    render_auth_screen()
    if st.session_state.get("authentication_status") is False:
        st.error("Username/password is incorrect")
    elif st.session_state.get("authentication_status") is None:
        st.info("Please enter your username and password, or go to Sign Up to create an account.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────
if "stop_flag" not in st.session_state:
    st.session_state.stop_flag = {"stop": False}
if "theme" not in st.session_state:
    st.session_state.theme = "Dark"

# ─────────────────────────────────────────────────────────────────────────────
# Theme token dictionaries
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Theme variable maps  (key → CSS custom-property name, value → colour/shadow)
# ─────────────────────────────────────────────────────────────────────────────
_THEME_VARS: dict[str, dict[str, str]] = {
    "Dark": {
        "bg":           "#0b1220",
        "bg2":          "#111827",
        "card":         "#1f2937",
        "card-hover":   "#263244",
        "input":        "#1f2937",
        "border":       "#374151",
        "border-card":  "#374151",
        "text1":        "#e5e7eb",
        "text2":        "#9ca3af",
        "text3":        "#6b7280",
        "muted":        "#4b5563",
        "accent":       "#3b82f6",
        "accent-hover": "#2563eb",
        "accent-text":  "#ffffff",
        "shadow":       "0 1px 4px rgba(0,0,0,.50), 0 0 0 1px rgba(255,255,255,.06)",
        "shadow-h":     "0 6px 20px rgba(0,0,0,.60), 0 0 0 1px rgba(255,255,255,.08)",
        "tag-bg":       "#1f2937",
        "tag-border":   "#374151",
        "bar-fill":     "#3b82f6",
        "bar-track":    "#1f2937",
        "divider":      "#1f2937",
        "p1-bg": "#2a2020", "p1-c": "#ff9b9b", "p1-b": "#4a2a2a",
        "p2-bg": "#2a2820", "p2-c": "#ffc164", "p2-b": "#4a3a20",
        "p3-bg": "#1f2937", "p3-c": "#9CA3AF", "p3-b": "#374151",
    },
    "Light": {
        "bg":           "#f9fafb",
        "bg2":          "#ffffff",
        "card":         "#ffffff",
        "card-hover":   "#f1f5f9",
        "input":        "#ffffff",
        "border":       "#e5e7eb",
        "border-card":  "#e5e7eb",
        "text1":        "#111827",
        "text2":        "#6b7280",
        "text3":        "#94a3b8",
        "muted":        "#9ca3af",
        "accent":       "#2563eb",
        "accent-hover": "#1d4ed8",
        "accent-text":  "#ffffff",
        "shadow":       "0 1px 4px rgba(0,0,0,.07), 0 0 0 1px rgba(0,0,0,.05)",
        "shadow-h":     "0 6px 20px rgba(0,0,0,.10), 0 0 0 1px rgba(0,0,0,.07)",
        "tag-bg":       "#f1f5f9",
        "tag-border":   "#e5e7eb",
        "bar-fill":     "#2563eb",
        "bar-track":    "#e5e7eb",
        "divider":      "#e5e7eb",
        "p1-bg": "#FEE2E2", "p1-c": "#B91C1C", "p1-b": "#FCA5A5",
        "p2-bg": "#FEF3C7", "p2-c": "#92400E", "p2-b": "#FCD34D",
        "p3-bg": "#F1F5F9", "p3-c": "#64748B", "p3-b": "#CBD5E1",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Static CSS — all rules reference var(--xxx); written once, never interpolated
# ─────────────────────────────────────────────────────────────────────────────
_STATIC_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Global ── */
html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important; }
#MainMenu, footer, header { visibility: hidden; }

.stApp {
  background: var(--bg) !important;
  color: var(--text1) !important;
  transition: background 0.35s ease, color 0.35s ease;
}
*, *::before, *::after {
  transition: background-color 0.35s ease, border-color 0.35s ease,
              color 0.35s ease, box-shadow 0.35s ease;
}

/* ── Block container ── */
.block-container {
  background: var(--bg) !important;
  color: var(--text1) !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--bg2) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--text1) !important; }
section[data-testid="stSidebar"] label {
  color: var(--text2) !important;
  font-size: 0.78rem !important;
  font-weight: 500 !important;
}

/* ── Inputs ── */
.stTextArea textarea, .stTextInput input, .stNumberInput input, .stSelectbox > div > div {
  background: var(--input) !important;
  color: var(--text1) !important;
  border-color: var(--border) !important;
  border-radius: 6px !important;
}
textarea, input, select {
  background: var(--input) !important;
  color: var(--text1) !important;
  border-color: var(--border) !important;
}
div[data-baseweb="input"] {
  background: var(--input) !important;
  border-color: var(--border) !important;
}
div[data-baseweb="input"] * {
  background: transparent !important;
  color: var(--text1) !important;
}
div[data-baseweb="input"] input {
  background: var(--input) !important;
  color: var(--text1) !important;
  -webkit-text-fill-color: var(--text1) !important;
  caret-color: var(--text1) !important;
}
.stNumberInput button, .stNumberInput [data-testid] button {
  background: var(--card) !important;
  color: var(--text1) !important;
  border-color: var(--border) !important;
}
.stNumberInput button:hover { background: var(--card-hover) !important; }
.stNumberInput > div > div {
  background: var(--input) !important;
  border-color: var(--border) !important;
}
.stDateInput > div, .stDateInput > div > div {
  background: var(--input) !important;
  border-color: var(--border) !important;
}
.stDateInput input {
  color: var(--text1) !important;
  -webkit-text-fill-color: var(--text1) !important;
}
div[data-baseweb="calendar"], div[data-baseweb="calendar"] * {
  background: var(--card) !important;
  color: var(--text1) !important;
}
/* Calendar day cells */
div[data-baseweb="calendar"] td,
div[data-baseweb="calendar"] th {
  background: var(--card) !important;
  color: var(--text1) !important;
}
div[data-baseweb="calendar"] [aria-selected="true"] {
  background: var(--accent) !important;
  color: var(--accent-text) !important;
}

/* ── Tabs ── */
div[data-testid="stTabs"] { background: var(--bg) !important; }
div[data-testid="stTabs"] > div { background: var(--bg) !important; }
[data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid var(--divider) !important;
  gap: 0px !important; padding: 0 !important;
}
[data-baseweb="tab-panel"] { background: var(--bg) !important; }
[data-baseweb="tab"] {
  border-radius: 0 !important;
  font-size: 0.78rem !important;
  font-weight: 500 !important;
  color: var(--text3) !important;
  border-bottom: 2px solid transparent !important;
  padding: 0.6rem 1rem !important;
  background: transparent !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--text1) !important;
  border-bottom-color: var(--accent) !important;
  font-weight: 600 !important;
  background: transparent !important;
}

/* ── Buttons ── */
.stButton > button {
  border-radius: 6px !important;
  font-weight: 600 !important;
  font-size: 0.82rem !important;
  border: 1px solid var(--border-card) !important;
  background: var(--card) !important;
  color: var(--text1) !important;
  transition: all 0.2s ease !important;
}
.stButton > button:hover {
  background: var(--card-hover) !important;
  box-shadow: var(--shadow-h) !important;
  transform: translateY(-1px);
}
.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {
  background: var(--accent) !important;
  color: var(--accent-text) !important;
  border-color: var(--accent) !important;
}
button[data-testid="stBaseButton-primary"]:hover {
  background: var(--accent-hover) !important;
  color: var(--accent-text) !important;
}
section[data-testid="stSidebar"] .stButton > button * {
  color: var(--text1) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] *,
section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] * {
  color: var(--accent-text) !important;
}

/* ── DataFrame ── */
div[data-testid="stDataFrame"] {
  border: 1px solid var(--border-card);
  border-radius: 8px;
  overflow: hidden;
}
.stDataFrame, .stDataFrame > div, .stDataFrame iframe {
  background: var(--card) !important;
  color: var(--text1) !important;
}
div[data-testid="stDataFrame"] div[data-testid="glide-data-grid-canvas"] {
  background: var(--card) !important;
}
/* Glide header & cells */
div[data-testid="stDataFrame"] th,
div[data-testid="stDataFrame"] td {
  background: var(--card) !important;
  color: var(--text1) !important;
  border-color: var(--border) !important;
}

/* ── Expander ── */
div[data-testid="stExpander"] {
  background: var(--card) !important;
  border: 1px solid var(--border-card) !important;
  border-radius: 8px !important;
}
div[data-testid="stExpander"] details { background: var(--card) !important; }
div[data-testid="stExpander"] summary { color: var(--text1) !important; }

/* ── JSON viewer ── */
div.stJson {
  background: var(--card) !important;
  color: var(--text1) !important;
  border-radius: 8px;
  border: 1px solid var(--border-card);
}
div.stJson > div { background: var(--card) !important; }
div.stJson pre, div.stJson code {
  background: var(--card) !important;
  color: var(--text2) !important;
}

/* ── Vertical blocks ── */
div[data-testid="stVerticalBlock"] { background: transparent !important; }

/* ── Markdown ── */
[data-testid="stMarkdownContainer"] {
  background: transparent !important;
  color: var(--text1) !important;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li {
  color: var(--text1) !important;
}

/* ── Selectbox dropdown ── */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] > div > div {
  background: var(--card) !important;
  border: 1px solid var(--border-card) !important;
  border-radius: 6px !important;
}
[data-baseweb="menu"],
[data-baseweb="menu"] > div,
[data-baseweb="menu"] ul,
div[data-baseweb="select"] [role="listbox"],
div[data-baseweb="select"] [role="listbox"] > div {
  background: var(--card) !important;
}
[data-baseweb="menu"] li, [role="option"] {
  background: var(--card) !important;
  color: var(--text1) !important;
}
[data-baseweb="menu"] li:hover,
[role="option"]:hover,
[aria-selected="true"][role="option"] {
  background: var(--card-hover) !important;
}

/* ── Spinner / status ── */
div[data-testid="stStatusWidget"] {
  background: var(--card) !important;
  color: var(--text1) !important;
}

/* ── Code blocks ── */
.stCodeBlock, pre {
  background: var(--card) !important;
  color: var(--text1) !important;
  border: 1px solid var(--border-card) !important;
  border-radius: 8px !important;
}

/* ── Alert / info ── */
div[data-testid="stAlert"] {
  background: var(--card) !important;
  color: var(--text1) !important;
  border-color: var(--border-card) !important;
}
div[data-testid="stAlert"] * {
  color: var(--text1) !important;
}

/* ── Native table ── */
.stTable, .stTable table { background: var(--card) !important; color: var(--text1) !important; }
.stTable th { background: var(--bg2) !important; color: var(--text2) !important; border-color: var(--border) !important; }
.stTable td { border-color: var(--divider) !important; color: var(--text1) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--muted); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text3); }

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  Custom component classes                                                 */
/* ═══════════════════════════════════════════════════════════════════════════ */

.page-title {
  font-size: 1.5rem; font-weight: 700; letter-spacing: -0.03em;
  color: var(--text1); margin: 0;
}
.page-sub {
  font-size: 0.82rem; color: var(--text3); margin: 0.15rem 0 1.2rem 0;
}
.sec-title {
  font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--muted); margin: 1.2rem 0 0.6rem 0;
}
.ctrl-box {
  background: var(--card); border: 1px solid var(--border-card);
  border-radius: 8px; padding: 0.8rem 0.9rem; margin-bottom: 0.65rem;
  box-shadow: var(--shadow);
}
.ctrl-hdr {
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 0.45rem;
}

/* Metric card */
.mc {
  background: var(--card); border: 1px solid var(--border-card);
  border-radius: 8px; padding: 1rem 1.2rem; text-align: center;
  box-shadow: var(--shadow);
}
.mc-v { font-size: 1.8rem; font-weight: 800; color: var(--text1); letter-spacing: -0.04em; }
.mc-l {
  font-size: 0.65rem; font-weight: 500; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text3); margin-top: 0.2rem;
}

/* Badges */
.bdg { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; }
.bdg-1 { background: var(--p1-bg); color: var(--p1-c); border: 1px solid var(--p1-b); }
.bdg-2 { background: var(--p2-bg); color: var(--p2-c); border: 1px solid var(--p2-b); }
.bdg-3 { background: var(--p3-bg); color: var(--p3-c); border: 1px solid var(--p3-b); }

/* Agent card */
.ag-card {
  background: var(--card); border: 1px solid var(--border-card);
  border-radius: 8px; padding: 0.9rem 1rem; margin: 0.35rem 0;
  box-shadow: var(--shadow); border-left: 3px solid var(--border);
}
.ag-card.active { border-left-color: var(--accent); background: var(--card-hover); box-shadow: var(--shadow-h); }
.ag-name { font-weight: 700; font-size: 0.88rem; color: var(--text1); }
.ag-desc { font-size: 0.75rem; color: var(--text3); line-height: 1.45; margin-top: 0.25rem; }
.ag-tools { margin-top: 0.45rem; }
.tool-t {
  display: inline-block; font-size: 0.65rem; font-weight: 600; padding: 1px 7px;
  border-radius: 4px; margin-right: 3px;
  background: var(--tag-bg); border: 1px solid var(--tag-border);
  color: var(--text2); font-family: 'SF Mono', 'Fira Code', monospace;
}
.ag-msg {
  font-size: 0.75rem; color: var(--text2);
  border-top: 1px solid var(--divider); padding-top: 0.4rem; margin-top: 0.45rem;
}
.dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent); margin-right: 5px; vertical-align: middle; }
.act-lbl { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--text3); }

/* State flow */
.sf {
  background: var(--card); border: 1px solid var(--border-card);
  border-radius: 8px; padding: 1.1rem;
  font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.75rem;
  line-height: 2.1; color: var(--text2); text-align: center;
  box-shadow: var(--shadow); margin-bottom: 1rem;
}
.sf .sn { color: var(--text1); font-weight: 600; }
.sf .se { color: var(--text3); font-style: italic; font-size: 0.7rem; }
.sf .sa { color: var(--muted); }
.sf .sf-any { font-size: 0.65rem; color: var(--muted); }
.sb {
  display: inline-block; padding: 3px 12px; border-radius: 6px;
  font-size: 0.75rem; font-weight: 700;
  font-family: 'SF Mono', 'Fira Code', monospace;
  background: var(--tag-bg); border: 1px solid var(--tag-border);
  color: var(--text1);
}

/* Message row */
.mr {
  display: flex; align-items: flex-start; gap: 0.65rem;
  padding: 0.5rem 0.7rem; border-radius: 6px; margin: 0.2rem 0;
  background: var(--card); border: 1px solid var(--border-card);
  font-size: 0.78rem;
}
.mr-ts { color: var(--muted); font-size: 0.67rem; white-space: nowrap;
  font-family: 'SF Mono','Fira Code',monospace; min-width: 58px; padding-top: 1px; }
.mr-tag {
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.05em;
  padding: 1px 6px; border-radius: 3px; white-space: nowrap;
  background: var(--tag-bg); border: 1px solid var(--tag-border);
  color: var(--text2);
}
.mr-txt { color: var(--text2); flex: 1; font-size: 0.76rem; line-height: 1.45; }
.mr-txt b { color: var(--text1); }
.mr-txt code {
  font-size: 0.7rem; color: var(--text3);
  background: var(--tag-bg); padding: 1px 4px; border-radius: 3px;
}

/* Bar chart */
.bl { display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 2px; }
.bl-n { color: var(--text2); }
.bl-v { color: var(--text1); font-weight: 600; }
.bt { background: var(--bar-track); border-radius: 4px; height: 6px;
  overflow: hidden; margin-bottom: 0.55rem; }
.bf { background: var(--bar-fill); height: 100%; border-radius: 4px;
  transition: width 0.5s ease; }

/* Task table */
.tt { width: 100%; border-collapse: separate; border-spacing: 0 4px; }
.tt thead th {
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--muted); text-align: left;
  padding: 6px 10px; border-bottom: 1px solid var(--divider);
}
.tt tbody tr { background: var(--card); transition: background 0.15s ease; }
.tt tbody tr:hover { background: var(--card-hover); }
.tt td {
  padding: 8px 10px; font-size: 0.78rem; color: var(--text1);
  border-bottom: 1px solid var(--divider);
}
.tt .dm { color: var(--text2); }
.tt .mn {
  font-family: 'SF Mono','Fira Code',monospace; font-size: 0.72rem; color: var(--text3);
}

/* Empty state */
.es { text-align: center; padding: 3rem 1rem; color: var(--muted); }
.es .ei { font-size: 2.5rem; margin-bottom: 0.5rem; }
.es .em { font-size: 0.82rem; color: var(--text3); }

/* Eval sidebar inline */
.eval-box { font-size: 0.75rem; line-height: 1.9; color: var(--text2); }
.eval-box b { color: var(--text1); }

/* Analysis panel */
.analysis-card {
  background: var(--card); border: 1px solid var(--border-card);
  border-radius: 10px; padding: 1.4rem 1.6rem; margin-bottom: 1rem;
  box-shadow: var(--shadow);
}
.analysis-heading {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 0.7rem 0;
  display: flex; align-items: center; gap: 0.45rem;
}
.analysis-heading .a-icon { font-size: 1rem; }
.analysis-summary {
  font-size: 0.88rem; line-height: 1.7; color: var(--text1);
  margin: 0; padding: 0;
}
.analysis-list { list-style: none; padding: 0; margin: 0; }
.analysis-list li {
  font-size: 0.82rem; color: var(--text1); line-height: 1.65;
  padding: 0.35rem 0; border-bottom: 1px solid var(--divider);
  display: flex; align-items: flex-start; gap: 0.4rem;
}
.analysis-list li:last-child { border-bottom: none; }
.analysis-list .li-bullet {
  color: var(--accent); font-size: 0.7rem; margin-top: 3px; flex-shrink: 0;
}
.analysis-table {
  width: 100%; border-collapse: separate; border-spacing: 0 3px;
}
.analysis-table thead th {
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--muted); text-align: left;
  padding: 6px 10px; border-bottom: 1px solid var(--divider);
}
.analysis-table tbody tr {
  background: var(--card); transition: background 0.15s ease;
}
.analysis-table tbody tr:hover { background: var(--card-hover); }
.analysis-table td {
  padding: 7px 10px; font-size: 0.78rem; color: var(--text1);
  border-bottom: 1px solid var(--divider);
}
.analysis-table .owner-cell { color: var(--accent); font-weight: 600; }
.analysis-table .dl-cell { color: var(--text2); font-family: 'SF Mono','Fira Code',monospace; font-size: 0.72rem; }
.analysis-empty {
  text-align: center; padding: 1.5rem; color: var(--text3);
  font-size: 0.82rem; font-style: italic;
}
.download-row { margin-top: 1rem; }
"""

# ─────────────────────────────────────────────────────────────────────────────
# apply_theme – emits CSS custom-properties + static rules
# ─────────────────────────────────────────────────────────────────────────────
def apply_theme(theme: str) -> None:
    """Inject CSS variables for *theme* ('Dark' or 'Light') + static rules."""
    v = _THEME_VARS.get(theme, _THEME_VARS["Dark"])
    var_lines = "\n".join(f"  --{k}: {val};" for k, val in v.items())
    st.markdown(
        f"<style>\n:root {{\n{var_lines}\n}}\n{_STATIC_CSS}\n</style>",
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    authenticator.logout("Logout", "sidebar")
    st.sidebar.markdown(f'Welcome *{st.session_state["username"]}*')
    theme = st.selectbox("Theme", ["Dark", "Light"],
                         index=0 if st.session_state.theme == "Dark" else 1)
    if theme != st.session_state.theme:
        st.session_state.theme = theme
        st.rerun()
    apply_theme(theme)


    st.markdown('<div class="ctrl-box"><div class="ctrl-hdr">Configuration</div>', unsafe_allow_html=True)
    seed = st.number_input("Seed", min_value=0, max_value=10_000_000, value=7, step=1)
    scenario_key = st.selectbox("Scenario", options=["(custom)"] + list(SCENARIOS.keys()))
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="ctrl-box"><div class="ctrl-hdr">Controls</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        start_btn = st.button("▶ Start", type="primary", use_container_width=True)
    with c2:
        stop_btn = st.button("■ Stop", use_container_width=True)
    reset_btn = st.button("↺ Reset", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if stop_btn:
        st.session_state.stop_flag["stop"] = True
    if reset_btn:
        st.session_state.stop_flag = {"stop": False}
        for k in ("last_output", "last_error", "last_eval"):
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown('<div class="ctrl-box"><div class="ctrl-hdr">Evaluation</div>', unsafe_allow_html=True)
    if st.button("Run 10 Scenarios", use_container_width=True):
        with st.spinner("Evaluating…"):
            st.session_state.last_eval = run_evaluation(seed=int(seed))
    if "last_eval" in st.session_state:
        ev: EvalResult = st.session_state.last_eval
        st.markdown(f"""
<div class="eval-box">
Scenarios: <b>{ev.scenarios}</b><br>
Owner Rate: <b>{ev.mean_owner_rate:.0%}</b><br>
Deadline Rate: <b>{ev.mean_deadline_rate:.0%}</b><br>
P1 Rate: <b>{ev.mean_p1_rate:.0%}</b><br>
Confidence: <b>{ev.mean_confidence:.2f}</b><br>
Jaccard: <b>{ev.mean_title_jaccard_vs_baseline:.2f}</b>
</div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="page-title">Meeting Notes → Action Items</p>', unsafe_allow_html=True)
st.markdown('<p class="page-sub">Multi-agent extraction pipeline · Parser → Classifier → Prioritizer</p>', unsafe_allow_html=True)

if scenario_key != "(custom)":
    default_text = SCENARIOS[scenario_key]
else:
    default_text = (
        "Alice: Action item: @Bob please send the updated deck by Friday.\n"
        "Bob: Sure, I will send it by Friday EOD.\n"
        "Carol: Let's schedule a sync next week to review progress.\n"
    )

with st.expander("📝 Transcript Input", expanded=True):
    raw = st.text_area("Paste transcript", value=default_text, height=160,
                       label_visibility="collapsed")


if start_btn:
    st.session_state.stop_flag["stop"] = False

    with st.spinner("Running pipeline…"):
        try:
            result = run_pipeline(
                raw,
                RunConfig(seed=int(seed)),
                stop_flag=st.session_state.stop_flag,
            )
            st.session_state.last_output = result
            st.session_state.last_error = None
            if result.run_id and result.items:
                tasks_dicts = [t.model_dump() for t in result.items]
                save_run(st.session_state["username"], result.run_id, str(date.today()), raw, tasks_dicts, result.analysis)
        except Exception as e:
            st.session_state.last_error = str(e)

if st.session_state.get("last_error"):
    st.error(f"Error: {st.session_state.last_error}")

out: RunOutput | None = st.session_state.get("last_output")

def render_table(data: list[dict]) -> str:
    if not data: return ""
    headers = list(data[0].keys())
    th = "".join(f"<th>{h}</th>" for h in headers)
    rows = ""
    for row in data:
        tds = "".join(f"<td>{str(row.get(h,'')).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</td>" for h in headers)
        rows += f"<tr>{tds}</tr>"
    return f'<div style="max-height:400px;overflow-y:auto;border:1px solid var(--border-card);border-radius:8px"><table class="tt" style="margin:0;width:100%"><thead><tr>{th}</tr></thead><tbody>{rows}</tbody></table></div>'

# ── TABS ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["🕒 Dashboard", "📊 Analysis", "Tasks", "Agents", "State", "Messages", "Metrics", "Logs", "JSON"])

# ── Dashboard ─────────────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown('<div class="sec-title">Your Meeting History</div>', unsafe_allow_html=True)
    runs = get_runs_for_user(st.session_state["username"])
    if not runs:
        st.info("No past meetings found. Run your first pipeline!")
    else:
        for r in runs:
            with st.expander(f"Meeting on {r['meeting_date']} - {len(r['tasks'])} tasks"):
                st.write(r["analysis"].get("meeting_summary", "No summary available."))
                st.code(json.dumps({"Action Items": r["tasks"]}, indent=2), language="json")

# ── Analysis ──────────────────────────────────────────────────────────────────
with tabs[1]:
    if out and out.analysis:
        analysis = out.analysis

        # Meeting Summary
        st.markdown(f'''
<div class="analysis-card">
  <div class="analysis-heading"><span class="a-icon">📝</span> Meeting Summary</div>
  <p class="analysis-summary">{analysis["meeting_summary"]}</p>
</div>''', unsafe_allow_html=True)

        # Key Discussion Points
        if analysis["key_discussion_points"]:
            li = "".join(f'<li><span class="li-bullet">●</span> {p}</li>' for p in analysis["key_discussion_points"])
            st.markdown(f'''
<div class="analysis-card">
  <div class="analysis-heading"><span class="a-icon">💬</span> Key Discussion Points</div>
  <ul class="analysis-list">{li}</ul>
</div>''', unsafe_allow_html=True)

        # Decisions Made
        if analysis["decisions_made"]:
            li = "".join(f'<li><span class="li-bullet">✔</span> {d}</li>' for d in analysis["decisions_made"])
            st.markdown(f'''
<div class="analysis-card">
  <div class="analysis-heading"><span class="a-icon">✅</span> Decisions Made</div>
  <ul class="analysis-list">{li}</ul>
</div>''', unsafe_allow_html=True)

        # Action Items table
        if analysis["action_items"]:
            rows = ""
            for ai in analysis["action_items"]:
                bdg_cls = {"P1": "bdg-1", "P2": "bdg-2"}.get(ai["priority"], "bdg-3")
                rows += f'''<tr>
  <td>{ai["task"]}</td>
  <td class="owner-cell">{ai["owner"]}</td>
  <td class="dl-cell">{ai["deadline"]}</td>
  <td><span class="bdg {bdg_cls}">{ai["priority"]}</span></td>
</tr>'''
            st.markdown(f'''
<div class="analysis-card">
  <div class="analysis-heading"><span class="a-icon">📋</span> Action Items</div>
  <table class="analysis-table">
    <thead><tr><th>Task</th><th>Owner</th><th>Deadline</th><th>Priority</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>''', unsafe_allow_html=True)

        # Open Questions
        if analysis["open_questions"]:
            li = "".join(f'<li><span class="li-bullet">❓</span> {q}</li>' for q in analysis["open_questions"])
            st.markdown(f'''
<div class="analysis-card">
  <div class="analysis-heading"><span class="a-icon">❓</span> Open Questions / Follow-ups</div>
  <ul class="analysis-list">{li}</ul>
</div>''', unsafe_allow_html=True)

        # Risks / Blockers
        if analysis["risks_blockers"]:
            li = "".join(f'<li><span class="li-bullet">⚠</span> {r}</li>' for r in analysis["risks_blockers"])
            st.markdown(f'''
<div class="analysis-card">
  <div class="analysis-heading"><span class="a-icon">⚠️</span> Risks / Blockers</div>
  <ul class="analysis-list">{li}</ul>
</div>''', unsafe_allow_html=True)

        # Download
        md_report = analysis_to_markdown(analysis)
        st.markdown('<div class="download-row">', unsafe_allow_html=True)
        st.download_button(
            label="📥 Download Analysis",
            data=md_report,
            file_name="meeting_analysis.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="es"><div class="ei">📊</div><div class="em">Click <b>▶ Start</b> to generate the meeting analysis</div></div>', unsafe_allow_html=True)

# ── Tasks ─────────────────────────────────────────────────────────────────────
with tabs[2]:
    if out and out.items:
        st.markdown('<div class="sec-title">Extracted Tasks</div>', unsafe_allow_html=True)
        def _pb(p):
            c = {"P1": "bdg-1", "P2": "bdg-2", "P3": "bdg-3"}.get(p, "bdg-3")
            return f'<span class="bdg {c}">{p}</span>'
        rows = ""
        for it in out.items:
            rows += f"""<tr>
<td class="mn">{it.id}</td>
<td>{it.title}</td>
<td class="dm">{it.owner}</td>
<td class="mn">{it.deadline or "—"}</td>
<td class="dm">{it.category}</td>
<td>{_pb(it.priority_label)}</td>
<td class="mn" style="text-align:center">{it.priority_score}</td>
<td class="mn" style="text-align:center">{it.confidence_score:.0%}</td>
</tr>"""
        st.markdown(f"""
<table class="tt"><thead><tr>
<th>ID</th><th>Title</th><th>Owner</th><th>Deadline</th>
<th>Category</th><th>Priority</th><th style="text-align:center">Score</th>
<th style="text-align:center">Conf.</th>
</tr></thead><tbody>{rows}</tbody></table>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="es"><div class="ei">📋</div><div class="em">Click <b>▶ Start</b> to extract action items</div></div>', unsafe_allow_html=True)

# ── Agents ────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown('<div class="sec-title">Agent Panel</div>', unsafe_allow_html=True)
    agents_info = [
        {"name":"parser","label":"Parser Agent","desc":"Reads raw transcript, identifies speaker turns and candidate action sentences with confidence scoring.","tools":["transcript_parse","extract_action_items"]},
        {"name":"classifier","label":"Classifier Agent","desc":"Assigns owner, deadline, and category to each item. Runs deduplication to remove near-duplicate tasks.","tools":["task_classify","deduplicate"]},
        {"name":"prioritizer","label":"Prioritizer Agent","desc":"Scores each task 1–10 on urgency/impact signals. Labels P1 (critical), P2 (high), P3 (normal).","tools":["priority_score"]},
        {"name":"summarizer","label":"Summary Agent","desc":"Generates an executive summary, key discussion points, and identifies decisions and risks.","tools":["meeting_summarize"]},
        {"name":"baseline","label":"Baseline Agent","desc":"Single-pass reference (no role separation, no dedup) used for metric comparison.","tools":["transcript_parse","extract_action_items","task_classify","priority_score"]},
    ]
    active = out.active_agent if out else ""
    for ag in agents_info:
        is_active = ag["name"] == active
        cls = " active" if is_active else ""
        act = '<span class="dot"></span><span class="act-lbl">Last Active</span>' if is_active else ""
        tt = "".join(f'<span class="tool-t">{t}</span>' for t in ag["tools"])
        msg = ""
        if out:
            for m in out.agent_messages:
                if m["agent"] == ag["name"]:
                    msg = m["message"]
        mh = f'<div class="ag-msg">→ {msg}</div>' if msg else ""
        st.markdown(f"""
<div class="ag-card{cls}">
<div style="display:flex;align-items:center;gap:0.5rem"><span class="ag-name">{ag['label']}</span> {act}</div>
<div class="ag-desc">{ag['desc']}</div>
<div class="ag-tools">{tt}</div>{mh}
</div>""", unsafe_allow_html=True)

# ── State ─────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown('<div class="sec-title">State Machine</div>', unsafe_allow_html=True)
    st.markdown("""
<div class="sf">
  <span class="sn">IDLE</span>
  <span class="sa"> ──</span><span class="se">start</span><span class="sa">──▶ </span>
  <span class="sn">PARSING</span>
  <span class="sa"> ──</span><span class="se">parsed</span><span class="sa">──▶ </span>
  <span class="sn">CLASSIFYING</span>
  <span class="sa"> ──</span><span class="se">classified</span><span class="sa">──▶ </span>
  <span class="sn">PRIORITIZING</span>
  <span class="sa"> ──</span><span class="se">prioritized</span><span class="sa">──▶ </span>
  <span class="sn">DONE</span>
  <br>
  <span class="sf-any">Any</span>
  <span class="sa"> ──</span><span class="se">error</span><span class="sa">──▶ </span>
  <span class="sn">ERROR</span>
  &nbsp;│&nbsp;
  <span class="sf-any">Any</span>
  <span class="sa"> ──</span><span class="se">stop</span><span class="sa">──▶ </span>
  <span class="sn">STOPPED</span>
</div>""", unsafe_allow_html=True)
    if out:
        st.markdown(f'Current: <span class="sb">{out.state_machine.state.value}</span>', unsafe_allow_html=True)
        data = [
            {"timestamp": tr.timestamp.strftime("%H:%M:%S.%f")[:-3],
             "from": tr.previous_state.value, "event": tr.event, "to": tr.next_state.value}
            for tr in out.state_machine.transitions
        ]
        st.markdown(render_table(data), unsafe_allow_html=True)
    else:
        st.markdown('<div class="es"><div class="ei">🔄</div><div class="em">Run pipeline to see transitions</div></div>', unsafe_allow_html=True)

# ── Messages ──────────────────────────────────────────────────────────────────
with tabs[5]:
    st.markdown('<div class="sec-title">Interaction Log</div>', unsafe_allow_html=True)
    if out:
        jp = os.path.join("runs", f"{out.run_id}.jsonl")
        if os.path.exists(jp):
            with open(jp, "r", encoding="utf-8") as f:
                evts = []
                for ln in f.readlines():
                    ln = ln.strip()
                    if ln:
                        try: evts.append(json.loads(ln))
                        except: pass
            for i, evt in enumerate(evts[-80:]):  # type: ignore[index]
                ts_raw: str = evt.get("ts", "")
                ts = ts_raw[-12:-4] if ts_raw else ""
                et = evt.get("type", "")
                p = evt.get("payload", {})
                if et == "agent_invoke": txt = f"<b>{p.get('agent','?')}</b> invoked"
                elif et == "tool_call":
                    tool = p.get("tool", "?")
                    inp = p.get("input", {})
                    with st.expander(f"{ts}  tool_call  {tool}", expanded=False):
                        st.json(inp)
                    txt = f"<b>{tool}</b>(input)"
                elif et == "tool_result":
                    tool = p.get("tool", "?")
                    outp = p.get("output", {})
                    with st.expander(f"{ts}  tool_result  {tool}", expanded=False):
                        st.json(outp)
                    txt = f"<b>{tool}</b> → <code>output</code>"
                elif et == "message": txt = p.get("text", str(json.dumps(p))[:80])
                elif et == "state_transition": txt = f"{p.get('previous_state','?')} → <b>{p.get('next_state','?')}</b> ({p.get('event','?')})"
                elif et == "metrics": txt = " · ".join(f"{k}={v}" for k, v in list(p.items())[:5])  # type: ignore[index]
                elif et == "run_start": txt = f"Run started · seed={p.get('seed','?')}"
                elif et == "run_end": txt = f"Run ended · {p.get('status','?')}"
                else: txt = str(json.dumps(p))[:100]
                st.markdown(f'<div class="mr"><span class="mr-ts">{ts}</span><span class="mr-tag">{et}</span><span class="mr-txt">{txt}</span></div>', unsafe_allow_html=True)
        else:
            st.info("No log file found.")
    else:
        st.markdown('<div class="es"><div class="ei">💬</div><div class="em">Run pipeline to see log</div></div>', unsafe_allow_html=True)

# ── Metrics ───────────────────────────────────────────────────────────────────
with tabs[6]:
    st.markdown('<div class="sec-title">Metrics Dashboard</div>', unsafe_allow_html=True)
    if out and out.metrics:
        m = out.metrics
        cols = st.columns(5)
        def _mc(col, val, label):
            col.markdown(f'<div class="mc"><div class="mc-v">{val}</div><div class="mc-l">{label}</div></div>', unsafe_allow_html=True)
        _mc(cols[0], m.get("items_count",0), "Tasks")
        _mc(cols[1], f"{m.get('owner_rate',0):.0%}", "Owner Rate")
        _mc(cols[2], f"{m.get('deadline_rate',0):.0%}", "Deadline Rate")
        _mc(cols[3], f"{m.get('p1_rate',0):.0%}", "P1 Rate")
        _mc(cols[4], f"{m.get('mean_confidence_score',0):.2f}", "Confidence")

        st.markdown('<div class="sec-title">Priority Distribution</div>', unsafe_allow_html=True)
        cl, cr = st.columns(2)
        with cl:
            st.markdown("**Multi-Agent Pipeline**")
            p1,p2,p3 = m.get("p1_count",0), m.get("p2_count",0), m.get("p3_count",0)
            tot = max(p1+p2+p3,1)
            for lbl, cnt in [("P1 Critical",p1),("P2 High",p2),("P3 Normal",p3)]:
                pct = cnt/tot
                st.markdown(f'<div class="bl"><span class="bl-n">{lbl}</span><span class="bl-v">{cnt} ({pct:.0%})</span></div><div class="bt"><div class="bf" style="width:{pct*100:.1f}%"></div></div>', unsafe_allow_html=True)
        with cr:
            st.markdown("**Baseline Comparison**")
            bl = m.get("baseline_items_count",0); ma = m.get("items_count",0); mx = max(ma,bl,1)
            for lbl, cnt in [("Multi-Agent",ma),("Baseline",bl)]:
                pct = cnt/mx
                st.markdown(f'<div class="bl"><span class="bl-n">{lbl}</span><span class="bl-v">{cnt}</span></div><div class="bt"><div class="bf" style="width:{pct*100:.1f}%"></div></div>', unsafe_allow_html=True)

        if "last_eval" in st.session_state:
            ev = st.session_state.last_eval
            st.markdown('<div class="sec-title">Per-Scenario Results</div>', unsafe_allow_html=True)
            data = [
                {"scenario": r.scenario_key, "items": r.items_count, "baseline": r.baseline_count,
                 "owner%": f"{r.owner_rate:.0%}", "deadline%": f"{r.deadline_rate:.0%}",
                 "P1%": f"{r.p1_rate:.0%}", "conf": f"{r.mean_confidence:.2f}",
                 "jaccard": f"{r.jaccard_vs_baseline:.2f}"}
                for r in ev.scenario_results
            ]
            st.markdown(render_table(data), unsafe_allow_html=True)
    else:
        st.markdown('<div class="es"><div class="ei">📊</div><div class="em">Run pipeline to see metrics</div></div>', unsafe_allow_html=True)

# ── Logs ──────────────────────────────────────────────────────────────────────
with tabs[7]:
    st.markdown('<div class="sec-title">Run Logs</div>', unsafe_allow_html=True)
    if out:
        st.markdown(f'**Run ID:** `{out.run_id}`')
        jp = os.path.join("runs", f"{out.run_id}.jsonl")
        if os.path.exists(jp):
            with open(jp, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                evts = [json.loads(line) for line in all_lines[-300:] if line.strip()]  # type: ignore[index]
            log_data = [{"ts": e.get("ts", ""), "type": e.get("type", ""), "payload": json.dumps(e.get("payload", {}))} for e in evts]
            st.markdown(render_table(log_data), unsafe_allow_html=True)
        st.markdown('<div class="sec-title" style="margin-top:1.5rem">Replay Past Run</div>', unsafe_allow_html=True)
        rd = "runs"
        run_files = [fname[:-6] for fname in os.listdir(rd) if fname.endswith(".jsonl")] if os.path.isdir(rd) else []
        past = sorted(run_files, reverse=True)[:50]  # type: ignore[index]
        if past:
            rid = st.selectbox("Select Run ID", past)
            if st.button("Load"):
                with open(os.path.join(rd, f"{rid}.jsonl"), "r", encoding="utf-8") as f:
                    evts = [json.loads(l) for l in f if l.strip()]
                    log_data = [{"ts": e.get("ts", ""), "type": e.get("type", ""), "payload": json.dumps(e.get("payload", {}))} for e in evts]
                    st.markdown(render_table(log_data), unsafe_allow_html=True)
    else:
        st.markdown('<div class="es"><div class="ei">📄</div><div class="em">Run pipeline to see logs</div></div>', unsafe_allow_html=True)

# ── JSON ──────────────────────────────────────────────────────────────────────
with tabs[8]:
    st.markdown('<div class="sec-title">Structured Output</div>', unsafe_allow_html=True)
    if out:
        st.code(json.dumps(out.output_json, indent=2), language="json")
        st.download_button("⬇ Download JSON",
            data=json.dumps(out.output_json, ensure_ascii=False, indent=2),
            file_name=f"{out.run_id}.tasks.json", mime="application/json",
            use_container_width=True)
    else:
        st.markdown('<div class="es"><div class="ei">📥</div><div class="em">Run pipeline to see JSON</div></div>', unsafe_allow_html=True)
