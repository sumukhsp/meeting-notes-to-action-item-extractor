import re

with open("app.py", "r", encoding="utf-8") as f:
    original = f.read()

debug_code = """
if start_btn:
    st.error("Button was successfully clicked!")
    st.session_state.stop_flag["stop"] = False
"""

patched = original.replace("if start_btn:\n    st.session_state.stop_flag[\"stop\"] = False", debug_code)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(patched)

print("Debug added")
