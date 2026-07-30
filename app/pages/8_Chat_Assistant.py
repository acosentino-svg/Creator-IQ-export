"""Chat Assistant — ask questions about creator activation in plain English."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

SRC_DIR = APP_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import os  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402
from creatoriq_dashboard.chat_engine import chat_turn  # noqa: E402

st.set_page_config(page_title="Chat Assistant", page_icon="💬", layout="wide")

st.title("💬 Chat Assistant")
st.caption(
    "Ask questions about your creator program in plain English. "
    "Results come from the same data powering the rest of this dashboard."
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

bundle = get_bundle()
ctx = bundle["activation_ctx"]

llm_enabled = bool(os.getenv("OPENAI_API_KEY", "").strip())
if llm_enabled:
    st.sidebar.success("LLM parsing enabled (OPENAI_API_KEY set)")
else:
    st.sidebar.info(
        "Using built-in question parser. Set **OPENAI_API_KEY** in `.env` for more flexible phrasing."
    )

# Example chips
st.markdown("**Try asking:**")
examples = st.columns(3)
example_questions = [
    "Give me 10 creators that activated for the first time this week",
    "How many creators are ghosts?",
    "Show creators who posted but never linked",
    "What's our activation funnel?",
    "List the outreach priority queue",
    "25 recently active VIP creators",
]
for i, q in enumerate(example_questions):
    if examples[i % 3].button(q, key=f"ex_{i}", use_container_width=True):
        st.session_state.pending_question = q

for turn in st.session_state.chat_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("table") is not None and not turn["table"].empty:
            st.dataframe(turn["table"], use_container_width=True, hide_index=True)
            st.download_button(
                "Download results CSV",
                turn["table"].to_csv(index=False).encode(),
                file_name="chat_results.csv",
                mime="text/csv",
                key=f"dl_{turn['id']}",
            )

prompt = st.session_state.pop("pending_question", None) or st.chat_input("Ask about creators, activation, segments…")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)

    response = chat_turn(prompt, ctx)

    with st.chat_message("assistant"):
        st.markdown(response.message)
        table_to_show = response.table
        if table_to_show is not None and not table_to_show.empty:
            st.dataframe(table_to_show, use_container_width=True, hide_index=True)
            st.download_button(
                "Download results CSV",
                table_to_show.to_csv(index=False).encode(),
                file_name="chat_results.csv",
                mime="text/csv",
                key=f"dl_latest_{len(st.session_state.chat_history)}",
            )
        if response.suggestions:
            st.caption("Other things to try: " + " · ".join(f"*{s}*" for s in response.suggestions[:3]))

    import pandas as pd

    st.session_state.chat_history.append(
        {
            "id": len(st.session_state.chat_history),
            "role": "user",
            "content": prompt,
        }
    )
    st.session_state.chat_history.append(
        {
            "id": len(st.session_state.chat_history),
            "role": "assistant",
            "content": response.message,
            "table": response.table.copy() if isinstance(response.table, pd.DataFrame) else None,
        }
    )

if st.sidebar.button("Clear chat"):
    st.session_state.chat_history = []
    st.rerun()
