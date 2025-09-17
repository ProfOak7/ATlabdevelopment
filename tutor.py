# tutor.py — BIO 205 (Human Anatomy) Tutor
# Deterministic logistics from bio205_knowledge/bio205_logistics.md
# (parses ::key=value lines), then model fallback for everything else.

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # Allow app to render without the SDK during setup

# ------------------------------ Config ---------------------------------------
DEFAULT_MODEL = os.getenv("BIO205_TUTOR_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = (
    "You are BIO 205 Tutor for Human Anatomy at Cuesta College. "
    "Be concise, friendly, and accurate. Prefer short Socratic guidance when appropriate. "
    "Give hints. When you use course logistics, append [Source: bio205_logistics.md]."
)

LOGISTICS_PATH = Path("bio205_knowledge/bio205_logistics.md")
SRC_TAG = "[Source: bio205_logistics.md]"

PACIFIC_TZNAME = "America/Los_Angeles"

# If lab-hour requirements are *also* added to the .md as:
#   ::lab_hours_1=2
#   ::lab_hours_2=3
# ...we'll use those. Otherwise the defaults below apply.
LAB_HOURS_DEFAULT: Dict[str, int] = {
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 4,
    "5": 4,
    "6": 3,
    "7": 4,
    "8": 2,
    "9": 2,
    "10": 2,
}

# ------------------------- Load logistics from .md ----------------------------

def _load_logistics_md() -> Dict[str, Any]:
    """
    Parse key-value pairs (::key=value) from bio205_logistics.md.
    Returns a dict for deterministic Q&A.
    """
    kb: Dict[str, Any] = {}
    if not LOGISTICS_PATH.exists():
        return kb
    try:
        text = LOGISTICS_PATH.read_text(encoding="utf-8")
    except Exception:
        return kb

    for line in text.splitlines():
        m = re.match(r"::([\w\-]+)=(.+)", line.strip())
        if m:
            kb[m.group(1).strip()] = m.group(2).strip()
    return kb

# ---------------------- Helpers for deterministic lookups ---------------------

def _extract_number_from_query(q: str) -> Optional[str]:
    # First bare digits
    for tok in re.findall(r"\d+", q):
        return tok
    # Also allow 'one'...'ten'
    words = {
        "one": "1","two":"2","three":"3","four":"4","five":"5",
        "six":"6","seven":"7","eight":"8","nine":"9","ten":"10",
    }
    for w, n in words.items():
        if re.search(rf"\b{w}\b", q):
            return n
    return None

def _md_lab_hours(kb: Dict[str, Any], num: str) -> Optional[int]:
    # Prefer explicit keys in the .md if present.
    val = kb.get(f"lab_hours_{num}")
    if val:
        try:
            return int(re.findall(r"\d+", val)[0])
        except Exception:
            pass
    # Fallback to defaults
    return LAB_HOURS_DEFAULT.get(num)

def _fmt_list(lines: List[str]) -> str:
    return "\n".join(f"- {ln}" for ln in lines)

# ---------------------- Deterministic answering -------------------------------

def _answer_from_md(q_user: str, kb: Dict[str, Any]) -> Optional[str]:
    """
    Answer logistics deterministically from parsed keys.
    """
    if not kb:
        return None

    q = (q_user or "").lower().strip()
    num = _extract_number_from_query(q)

    # Normalize intent flags
    asks_final = "final" in q
    asks_lecture = ("lecture" in q) or (("exam" in q or "test" in q) and "lab" not in q and not "practical" in q)
    asks_lab = ("lab" in q) or ("practical" in q)

    # ---- Lecture Exams (incl. Final) ----
    if asks_lecture or asks_final:
        if asks_final or ("final exam" in q):
            lines = []
            for campus in ("NCC", "SLO"):
                date = kb.get(f"final_exam_date_{campus}")
                time = kb.get(f"final_exam_time_{campus}")
                if date:
                    lines.append(f"{campus}: {date}" + (f" {time}" if time else ""))
            if lines:
                return "**Final Exam**\n" + _fmt_list(lines) + f"\n{SRC_TAG}"

        if num:
            lines = []
            for campus in ("NCC", "SLO"):
                date = kb.get(f"lecture_exam_{num}_date_{campus}")
                time = kb.get(f"lecture_exam_{num}_time_{campus}")
                if date:
                    lines.append(f"{campus}: {date}" + (f" {time}" if time else ""))
            if lines:
                return f"**Lecture Exam {num}**\n" + _fmt_list(lines) + f"\n{SRC_TAG}"

    # ---- Lab Exams (dates) ----
    if asks_lab:
        if num:
            lines = []
            for campus in ("NCC", "SLO"):
                date = kb.get(f"lab_exam_{num}_date_{campus}")
                if date:
                    lines.append(f"{campus}: {date}")
            if lines:
                # Include hours if the question hints at requirements
                if "hour" in q or "time requirement" in q or "lab time" in q:
                    hrs = _md_lab_hours(kb, num)
                    req = f"\nMinimum lab hours required before Lab Exam {num}: **{hrs}**." if hrs else ""
                else:
                    req = ""
                return f"**Lab Exam {num}**\n" + _fmt_list(lines) + f"{req}\n{SRC_TAG}"

        # Generic “when is lab exam 1”, “lab exam schedule” without number:
        if "schedule" in q or "when" in q:
            # Show the next few items succinctly
            rows = []
            for i in range(1, 11):
                s = str(i)
                ncc = kb.get(f"lab_exam_{s}_date_{NCC}") if (NCC:= "NCC") else None  # noqa: E731
                slo = kb.get(f"lab_exam_{s}_date_{SLO}") if (SLO:= "SLO") else None  # noqa: E731
                if ncc or slo:
                    rows.append(f"Lab Exam {s} — " +
                                ", ".join([f"NCC: {ncc}" if ncc else None,
                                           f"SLO: {slo}" if slo else None]).replace(", None","").replace("None, ",""))
            if rows:
                return "**Lab Exam Schedule (dates)**\n" + _fmt_list(rows[:6]) + f"\n{SRC_TAG}"

    # ---- Lab Hours requirement (e.g., 'How many hours before Lab Exam 4?') ----
    if ("hour" in q or "hours" in q) and ("lab" in q or "practical" in q):
        if num:
            hrs = _md_lab_hours(kb, num)
            if hrs is not None:
                return f"Minimum lab hours required before **Lab Exam {num}**: **{hrs}**.\n[Source: Lab Objectives]"
        # If no number given, provide a short range and tip:
        return ("Minimum hours vary by exam (typically **2–4 hours**). "
                "Ask about a specific lab exam number, e.g., 'How many hours for Lab Exam 3?'\n[Source: Lab Objectives]")

    # ---- Office hours ----
    if "office hour" in q or "office-hours" in q or q == "office hours":
        ncc = kb.get("office_hours_NCC")
        slo = kb.get("office_hours_SLO")
        if ncc or slo:
            lines = []
            if ncc: lines.append(f"NCC: {ncc}")
            if slo: lines.append(f"SLO: {slo}")
            return "**Office Hours (Fall 2025)**\n" + _fmt_list(lines) + f"\n{SRC_TAG}"

    # ---- Drop / Withdrawal dates ----
    if "drop" in q or "withdraw" in q or "withdrawal" in q:
        no_w = kb.get("drop_no_W")
        w = kb.get("withdraw_with_W")
        lines = []
        if no_w: lines.append(f"Last day to drop **without a W**: {no_w}")
        if w: lines.append(f"Last day to **withdraw with a W**: {w}")
        if lines:
            return "**Deadlines**\n" + _fmt_list(lines) + f"\n{SRC_TAG}"

    # ---- AT Lab campus/rooms (quick facts) ----
    if "at lab" in q or ("lab" in q and "where" in q):
        lines = [
            "SLO AT Lab: Room 2201",
            "NCC AT Lab: Room N2438",
            "Lab exams: Canvas quiz (open-note) + oral exam in AT Lab (closed-note, by appointment).",
            "Missed minimum hours cost **5 points per hour**."
        ]
        return "**AT Lab Info**\n" + _fmt_list(lines) + f"\n{SRC_TAG}"

    return None

# ----------------------------- UI (Streamlit) --------------------------------

def _mode_instruction(mode: str) -> str:
    return {
        "Explainer": "Explain clearly with one quick question to check assumptions. Include a brief recap.",
        "Quizzer": "Ask 2–4 short questions, give immediate feedback, then a 1-sentence summary.",
    }.get(mode, "Explain clearly and check understanding briefly.")

def render_chat(
    course_hint: str = "BIO 205: Human Anatomy",
    show_sidebar_controls: bool = True,
) -> None:
    """Renders a chat panel. Deterministic logistics first; otherwise model-only."""

    # Load logistics MD once per render
    kb = _load_logistics_md()

    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if (OpenAI and api_key) else None
    if client is None:
        st.caption("_Tip: set OPENAI_API_KEY for live model answers beyond logistics._")

    # Sidebar controls
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

    user_text = st.chat_input("Ask about BIO 205 (e.g., 'When is Lab Exam 1?' or 'How many hours before Lab Exam 4?')")
    if not user_text:
        return

    st.session_state.bio205_chat.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # 1) Deterministic logistics first
    direct = _answer_from_md(user_text, kb)
    if direct:
        with st.chat_message("assistant"):
            st.markdown(direct)
        st.session_state.bio205_chat.append({"role": "assistant", "content": direct})
        return

    # 2) Otherwise, model fallback (general tutoring)
    dev = (
        f"Mode: {mode}. {_mode_instruction(mode)}\n"
        f"Course: {course_hint}\n"
        f"When answering logistics/objectives, prefer and cite 'bio205_logistics.md'."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "developer", "content": dev},
    ]

    # Keep last few turns for context
    short_hist = [m for m in st.session_state.bio205_chat if m["role"] in ("user", "assistant")][-8:]
    messages.extend(short_hist)

    with st.chat_message("assistant"):
        if client is None:
            st.markdown("_Demo mode: logistics answered deterministically; set OPENAI_API_KEY for full answers._")
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
