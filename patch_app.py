import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Imports
imports = """import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from src.db import save_run, get_runs_for_user
"""
content = re.sub(r"import streamlit as st\n", imports, content)

# 2. Add authentication at the top of the auth section
auth_block = """# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────
with open('.streamlit/config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config.get('preauthorized')
)

try:
    authenticator.login()
except Exception as e:
    st.error(e)

if st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")
    st.stop()

"""
content = content.replace("# ─────────────────────────────────────────────────────────────────────────────\n# Session state", auth_block + "# ─────────────────────────────────────────────────────────────────────────────\n# Session state")

# 3. Add to sidebar
sidebar_ext = """    authenticator.logout("Logout", "sidebar")
    st.sidebar.markdown(f'Welcome *{st.session_state["username"]}*')
"""
content = content.replace("with st.sidebar:\n    theme = st.selectbox", "with st.sidebar:\n" + sidebar_ext + "    theme = st.selectbox")

# 4. Save to DB
save_logic = """            st.session_state.last_error = None
            if result.run_id and result.items:
                tasks_dicts = [t.model_dump() for t in result.items]
                save_run(st.session_state["username"], result.run_id, str(date.today()), raw, tasks_dicts, result.analysis)
"""
content = content.replace("            st.session_state.last_error = None\n", save_logic)

# 5. Add Dashboard tab and shift indices
content = content.replace('tabs = st.tabs(["📊 Analysis"', 'tabs = st.tabs(["🕒 Dashboard", "📊 Analysis"')
for i in range(7, -1, -1):
    content = content.replace(f"with tabs[{i}]:", f"with tabs[{i+1}]:")

dash_block = """# ── Dashboard ─────────────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown('<div class="sec-title">Your Meeting History</div>', unsafe_allow_html=True)
    runs = get_runs_for_user(st.session_state["username"])
    if not runs:
        st.info("No past meetings found. Run your first pipeline!")
    else:
        for r in runs:
            with st.expander(f"Meeting on {r['meeting_date']} - {len(r['tasks'])} tasks"):
                st.write(r["analysis"].get("meeting_summary", "No summary available."))
                st.json({"Action Items": r["tasks"]})

"""
content = content.replace("# ── Analysis ──────────────────────────────────────────────────────────────────", dash_block + "# ── Analysis ──────────────────────────────────────────────────────────────────")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied.")
