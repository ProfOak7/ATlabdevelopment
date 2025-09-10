# tutor.py — BIO 205 (Human Anatomy) — Fresh Build
# Streamlit chat assistant with deterministic logistics answers from syllabus-like files
# -------------------------------------------------------------------------------
# Usage:
#   streamlit run tutor.py
#
# Sidebar tips:
#   • Set a knowledge folder path (defaults to env BIO205_KNOWLEDGE_DIR or ./knowledge)
#   • Click “🔄 Reindex logistics” after changing files or uploading
#   • (Optional) Set a preferred section string (e.g., a CRN like 70865) to prioritize

import os
import re
import json
import pathlib
from typing import List, Dict, Any, Optional

import streamlit as st
from openai import OpenAI

# ------------------------------ Config ---------------------------------------
DEFAULT_MODEL = os.getenv("BIO205_TUTOR_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = (
    "You are BIO 205 Tutor for Human Anatomy at Cuesta College. "
    "Be concise, friendly, and accurate. Prefer Socratic guidance (ask one quick "
    "question before explaining when appropriate). Give hints. "
    "When you use course knowledge, append [Source: <filename>]. "
    "For logistics or lab objectives, cite [Source: bio205_logistics.md] if information is present there."
)

# Allow explicit include list via env/Secrets (semicolon separated)
_LOGISTICS_FILELIST = os.getenv("BIO205_LOGISTICS_FILES", "").strip()

# Default knowledge directory
_DEFAULT_KNOWLEDGE_DIR = os.getenv("BIO205_KNOWLEDGE_DIR", str(pathlib.Path("./knowledge").resolve()))

def _load_and_index_logistics(knowledge_dir: Optional[str]) -> None:
    """Scan knowledge_dir for syllabus/logistics files, extract logistics, and cache them."""
    st.session_state.bio205_logistics = None
    if not knowledge_dir:
        return
    base = pathlib.Path(knowledge_dir)
    if not base.exists():
        return

    collected = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if not _is_logistics_file(p):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        data = _extract_logistics_from_text(txt, p.name)
        collected.append(data)

    if collected:
        # Prefer a selected section/CRN if user stored one
        sec = st.session_state.get("bio205_section")
        if sec:
            collected.sort(key=lambda b: 0 if sec and sec in (b.get("source", "")) else 1)
        st.session_state.bio205_logistics = collected


def _answer_from_indexed_logistics(q: str) -> Optional[str]:
    """Answer logistics Qs deterministically from cached syllabus extracts."""
    info = st.session_state.get("bio205_logistics")
    if not info:
        return None

    ql = q.lower().strip()

    # Prefer selected section/CRN substring in source or entries
    sec_pref = st.session_state.get("bio205_section")
    if sec_pref:
        # Stable ordering: blocks that contain the section string first
        def block_score(block: dict) -> int:
            if sec_pref and sec_pref in block.get("source", ""):
                return 0
            return 1
        info = sorted(info, key=block_score)

    # Detect specific exam/practical number in the question
    num = None
    mnum = re.search(r"(?:exam|practical)\s*(\d+)", ql, re.I)
    if mnum:
        num = mnum.group(1)

    def fmt(entry, src):
        label = entry["name"]
        if entry.get("crn"):
            if entry.get("section"):
                label = f"{label} (CRN {entry['crn']}, {entry['section']})"
            else:
                label = f"{label} (CRN {entry['crn']})"
        bits = [label]
        if entry.get("date"):
            bits.append(entry["date"])
        if entry.get("time"):
            bits.append(entry["time"])
        return "- " + " ".join(bits) + f"  \n[Source: {src}]"

    # Exams/Practicals
    if any(k in ql for k in ["exam", "midterm", "test", "practical"]):
        lines = []
        for block in info:
            src = block["source"]
            items = block.get("exams", []) + block.get("lab_practicals", [])
            for e in items:
                if num and e.get("number") != num:
                    continue
                # If no number asked and this entry has neither date nor time, skip to avoid noise
                if not num and not (e.get("date") or e.get("time")):
                    continue
                lines.append(fmt(e, src))
        if lines:
            title = f"**{('Exam ' + num) if num else 'Exams/Practicals'}**"
            return title + "\n" + "\n".join(lines)

    # Office hours
    if "office hour" in ql or "office-hours" in ql:
        for block in info:
            if block.get("office_hours"):
                return f"**Office Hours**  \n{block['office_hours']}  \n[Source: {block['source']}]"

    # Late policy
    if "late policy" in ql or "late work" in ql or ("late" in ql and "policy" in ql):
        for block in info:
            if block.get("late_policy"):
                return f"**Late Policy**  \n{block['late_policy']}  \n[Source: {block['source']}]"

    # Quizzes policy lines
    if "quiz" in ql or "quizzes" in ql:
        for block in info:
            if block.get("quizzes_policy"):
                return f"**Quizzes**  \n{block['quizzes_policy']}  \n[Source: {block['source']}]"

    # Generic due date lines
    if "due" in ql:
        lines = []
        for block in info:
            for ln in block.get("due_lines", []):
                lines.append(f"- {ln}  \n[Source: {block['source']}]")
        if lines:
            return "**Due items found in syllabus**\n" + "\n".join(lines)

    return None


# ----------------------------- UI (Streamlit) --------------------------------

def _mode_instruction(mode: str) -> str:
    return {
        "Explainer":"Explain clearly with analogies and a quick misconception check tied to everyday life.",
        "Quizzer":  "Ask 2–4 short questions, give immediate feedback, then a brief recap.",        
    }.get(mode, "Explain clearly and check understanding briefly.")


def render_chat(
    course_hint: str = "BIO 205: Human Anatomy",
    show_sidebar_controls: bool = True,
) -> None:
    """Renders a chat panel. Deterministic logistics first; otherwise model-only."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Set OPENAI_API_KEY to enable live answers.")

    if show_sidebar_controls:
        st.sidebar.subheader("BIO 205 Tutor")
        mode = st.sidebar.radio("Mode", ["Explainer", "Quizzer"], index=0)
        temperature = st.sidebar.slider("Creativity", 0.0, 1.0, 0.4)

        # Knowledge folder controls
        if "bio205_knowledge_dir" not in st.session_state:
            st.session_state.bio205_knowledge_dir = _DEFAULT_KNOWLEDGE_DIR

        if st.sidebar.button("🔄 Reindex logistics"):
            _load_and_index_logistics(st.session_state["bio205_knowledge_dir"])
            cnt = 0
            if st.session_state.get("bio205_logistics"):
                cnt = sum(len(b.get("exams", [])) + len(b.get("lab_practicals", [])) for b in st.session_state["bio205_logistics"])
            st.sidebar.success(f"Reindexed. Found {cnt} exam/practical entries.")
    else:
        mode, temperature = "Coach", 0.4

    if "bio205_chat" not in st.session_state:
        st.session_state.bio205_chat = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Print prior turns
    for m in st.session_state.bio205_chat:
        if m["role"] == "user":
            with st.chat_message("user"):
                st.markdown(m["content"])
        elif m["role"] == "assistant":
            with st.chat_message("assistant"):
                st.markdown(m["content"])

    user_text = st.chat_input("Ask about BIO 205 (e.g., 'When is Exam 1?' or 'What’s on Lab Exam 5?')")
    if not user_text:
        return

    # Echo user
    st.session_state.bio205_chat.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # 1) Deterministic logistics/objectives answers FIRST
    direct = _answer_from_indexed_logistics(user_text)
    if direct:
        with st.chat_message("assistant"):
            st.markdown(direct)
        st.session_state.bio205_chat.append({"role": "assistant", "content": direct})
        return

    # 2) Otherwise, normal model chat (no retrieval)
    dev = (
        f"Mode: {mode}. {_mode_instruction(mode)}\n"
        f"Course: {course_hint}\n"
        f"When answering logistics/objectives, prefer and cite 'bio205_logistics.md'."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "developer", "content": dev},
    ]

    # Keep last ~8 turns for cost control
    short_hist = [m for m in st.session_state.bio205_chat if m["role"] in ("user", "assistant")][-8:]
    messages.extend(short_hist)

    with st.chat_message("assistant"):
        if client is None:
            st.markdown("_Demo mode: set OPENAI_API_KEY for live answers._")
            return
        try:
            resp = client.responses.create(model=DEFAULT_MODEL, input=messages, temperature=temperature)
            reply = resp.output_text
        except Exception as e:
            reply = f"Sorry, I ran into an error: `{e}`"
        st.markdown(reply)
        st.session_state.bio205_chat.append({"role": "assistant", "content": reply})


# --------------------------- Entrypoint (Streamlit) ---------------------------
if __name__ == "__main__":
    st.set_page_config(page_title="BIO 205 Tutor", page_icon="🧠", layout="wide")
    st.title("BIO 205 Tutor — Human Anatomy")

    # Auto-load knowledge on first run
    if st.session_state.get("_bootstrapped") is None:
        _load_and_index_logistics(_DEFAULT_KNOWLEDGE_DIR)
        st.session_state._bootstrapped = True

    render_chat()

