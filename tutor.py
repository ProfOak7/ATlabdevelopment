# tutor.py — BIO 205 (Human Anatomy) — JSON‑Only, Deterministic
# Streamlit chat assistant that answers logistics from a *structured JSON* in secrets,
# then falls back to the model for everything else. No file I/O, no regex parsing.
# -------------------------------------------------------------------------------
import os
from typing import Dict, Any, List, Optional

import streamlit as st
from openai import OpenAI

# ------------------------------ Config ---------------------------------------
DEFAULT_MODEL = os.getenv("BIO205_TUTOR_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = (
    "You are BIO 205 Tutor for Human Anatomy at Cuesta College. "
    "Be concise, friendly, and accurate. Prefer Socratic guidance (ask one quick "
    "question before explaining when appropriate). Give hints. "
    "When you use course knowledge, append [Source: bio205_logistics.json]."
)

# ------------------------- Load structured logistics -------------------------

def _load_logistics_json() -> Dict[str, Any]:
    """Load JSON from secrets. Returns an empty structure if missing."""
    data = st.secrets.get("BIO205_LOGISTICS_JSON")
    if not data:
        return {
            "exams": [],
            "lab_practicals": [],
            "office_hours": None,
            "late_policy": None,
            "quizzes_policy": None,
            "due_lines": [],
        }
    # `st.secrets` may give a dict already; otherwise it's a string containing JSON
    if isinstance(data, str):
        try:
            import json
            return json.loads(data)
        except Exception:
            return {"exams": [], "lab_practicals": [], "office_hours": None, "late_policy": None, "quizzes_policy": None, "due_lines": []}
    if isinstance(data, dict):
        return data
    # Fallback
    return {"exams": [], "lab_practicals": [], "office_hours": None, "late_policy": None, "quizzes_policy": None, "due_lines": []}


# ---------------------- Deterministic answering -------------------------------

def _answer_from_json(q: str, kb: Dict[str, Any]) -> Optional[str]:
    src = "bio205_logistics.json"
    ql = (q or "").lower().strip()

    def fmt(entry: Dict[str, Any]) -> str:
        label = entry.get("name") or ""
        crn = entry.get("crn")
        section = entry.get("section")
        if crn:
            if section:
                label = f"{label} (CRN {crn}, {section})"
            else:
                label = f"{label} (CRN {crn})"
        bits: List[str] = [label]
        if entry.get("date"):
            bits.append(entry["date"])
        if entry.get("time"):
            bits.append(entry["time"])
        return "- " + " ".join(bits) + f"  
[Source: {src}]"

    # detect number tokens like "1" in "Exam 1"
    num: Optional[str] = None
    for tok in ql.replace("?", "").split():
        if tok.isdigit():
            num = tok
            break

    # --- Exams / Practicals ---
    if any(k in ql for k in ("exam", "midterm", "test", "practical", "final")):
        lines: List[str] = []
        items = list(kb.get("exams", [])) + list(kb.get("lab_practicals", []))
        for e in items:
            name_low = (e.get("name") or "").lower()
            # explicit final request narrows to finals
            if "final" in ql and "final" not in name_low:
                continue
            if num and (e.get("number") != num):
                continue
            # If no number requested, still allow finals or any entry with date/time
            if not num and not (e.get("date") or e.get("time")):
                continue
            lines.append(fmt(e))
        if lines:
            title = f"**{('Exam ' + num) if (num and 'final' not in ql) else ('Final Exam' if 'final' in ql else 'Exams/Practicals')}**"
            return title + "
" + "
".join(lines)

    # --- Office hours ---
    if "office hour" in ql or "office-hours" in ql or ql == "office hours":
        oh = kb.get("office_hours")
        if oh:
            return f"**Office Hours**  
{oh}  
[Source: {src}]"

    # --- Late policy ---
    if "late policy" in ql or "late work" in ql or ("late" in ql and "policy" in ql):
        lp = kb.get("late_policy")
        if lp:
            return f"**Late Policy**  
{lp}  
[Source: {src}]"

    # --- Quizzes policy ---
    if "quiz" in ql or "quizzes" in ql:
        qp = kb.get("quizzes_policy")
        if qp:
            return f"**Quizzes**  
{qp}  
[Source: {src}]"

    # --- Generic due lines ---
    if "due" in ql:
        lines2: List[str] = []
        for ln in kb.get("due_lines", []) or []:
            lines2.append(f"- {ln}  
[Source: {src}]")
        if lines2:
            return "**Due items found**
" + "
".join(lines2)

    return None


# ----------------------------- UI (Streamlit) --------------------------------

def _mode_instruction(mode: str) -> str:
    return {
        "Explainer": "Explain clearly with analogies and a quick misconception check tied to everyday life.",
        "Quizzer": "Ask 2–4 short questions, give immediate feedback, then a brief recap.",
    }.get(mode, "Explain clearly and check understanding briefly.")


def render_chat(
    course_hint: str = "BIO 205: Human Anatomy",
    show_sidebar_controls: bool = True,
) -> None:
    """Renders a chat panel. Deterministic logistics first; otherwise model-only."""

    # Load JSON logistics once per render
    kb = _load_logistics_json()

    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Set OPENAI_API_KEY to enable live answers.")

    # Minimal sidebar
    if show_sidebar_controls:
        st.sidebar.subheader("BIO 205 Tutor")
        mode = st.sidebar.radio("Mode", ["Explainer", "Quizzer"], index=0)
        temperature = st.sidebar.slider("Creativity", 0.0, 1.0, 0.4)
    else:
        mode, temperature = "Explainer", 0.4

    # Chat history
    if "bio205_chat" not in st.session_state:
        st.session_state.bio205_chat = [{"role": "system", "content": SYSTEM_PROMPT}]

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

    st.session_state.bio205_chat.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # 1) Deterministic logistics first
    direct = _answer_from_json(user_text, kb)
    if direct:
        with st.chat_message("assistant"):
            st.markdown(direct)
        st.session_state.bio205_chat.append({"role": "assistant", "content": direct})
        return

    # 2) Otherwise, model fallback
    dev = (
        f"Mode: {mode}. {_mode_instruction(mode)}
"
        f"Course: {course_hint}
"
        f"When answering logistics/objectives, prefer and cite 'bio205_logistics.json'."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "developer", "content": dev},
    ]

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
    render_chat()
