# tutor.py — BIO 205 (Human Anatomy) — Simplified
# Streamlit chat assistant with **deterministic logistics** answers from a single
# secrets-backed syllabus file, plus model fallback. Minimal sidebar. No uploads,
# no section pickers, no directory pickers.
# -------------------------------------------------------------------------------
# Usage:
#   • Put your full syllabus/logistics Markdown into Streamlit secrets as
#       BIO205_LOGISTICS_MD
#   • (Optional) Put a custom knowledge dir path in secrets as
#       BIO205_KNOWLEDGE_DIR (defaults to ./bio205_knowledge)
#   • Run:  streamlit run tutor.py

import os
import pathlib
from typing import Dict, Any, List, Optional

import streamlit as st
from openai import OpenAI

# ------------------------------ Config ---------------------------------------
DEFAULT_MODEL = os.getenv("BIO205_TUTOR_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = (
    "You are BIO 205 Tutor for Human Anatomy at Cuesta College. "
    "Be concise, friendly, and accurate. Prefer Socratic guidance (ask one quick "
    "question before explaining when appropriate). NEVER reveal answer keys; give hints "
    "instead. When you use course knowledge, append [Source: <filename>]. "
    "For logistics or lab objectives, cite [Source: bio205_logistics.md] if information is present there."
)

# Single, canonical knowledge dir definition (read from secrets, with a default)
DEFAULT_KNOWLEDGE_DIR = st.secrets.get("BIO205_KNOWLEDGE_DIR", str(pathlib.Path("./bio205_knowledge").resolve()))

# -------------------------- Tiny parser (no regex) ----------------------------
# This parser is purpose-built for the provided syllabus format. It avoids heavy
# regex and focuses on simple line-prefix/state logic. If your format changes,
# update the few "starts with" checks below.

def _ensure_logistics_loaded_once() -> None:
    """Ensure the syllabus file exists on disk and index it once per session."""
    if st.session_state.get("bio205_logistics_indexed"):
        return

    base = pathlib.Path(DEFAULT_KNOWLEDGE_DIR)
    base.mkdir(parents=True, exist_ok=True)
    f = base / "bio205_logistics.md"

    secret_key = "BIO205_LOGISTICS_MD"
    if secret_key in st.secrets and not f.exists():
        f.write_text(st.secrets[secret_key], encoding="utf-8")

    # Always (re)load into memory once per session
    if f.exists():
        text = f.read_text(encoding="utf-8", errors="ignore")
        st.session_state.bio205_logistics_blocks = [_parse_logistics(text, f.name)]
    else:
        st.session_state.bio205_logistics_blocks = []

    st.session_state.bio205_logistics_indexed = True


def _parse_logistics(text: str, source_name: str) -> Dict[str, Any]:
    """Parse the simplified syllabus into structured dictionaries.
    Expected key shapes in output:
      - exams:          [{name, number, date, time, crn, section, kind}]
      - lab_practicals: same
      - office_hours:   str | None
      - late_policy:    str | None
      - quizzes_policy: str | None
      - due_lines:      [str]
    """
    lines = [ln.rstrip("
") for ln in text.splitlines()]

    # State flags
    in_lecture_exams = False
    in_lab_exams = False
    in_office_hours = False
    current_crn: Optional[str] = None
    current_section: Optional[str] = None

    data: Dict[str, Any] = {
        "source": source_name,
        "exams": [],
        "lab_practicals": [],
        "office_hours": None,
        "late_policy": None,
        "quizzes_policy": None,
        "due_lines": [],
    }

    def push_exam(line: str, list_name: str, kind: str) -> None:
        # Patterns like: "Exam 1: Tue 9/9" or "Final Exam: Tue 12/9, 4:30–6:30 PM, Room N2401"
        name = line.split(":", 1)[0].strip()  # "Exam 1" or "Final Exam"
        rest = line[len(name) + 1 :].strip() if ":" in line else ""
        number: Optional[str] = None
        if name.lower().startswith("exam "):
            num_part = name[5:].strip()
            number = num_part if num_part.isdigit() else None
        # Extract date/time heuristically from the rest of the line
        date = None
        time = None
        if rest:
            # Stop at first comma to split date vs time/location
            parts = [p.strip() for p in rest.split(",")]
            # The first piece is the date phrase (e.g., "Tue 9/9")
            if parts:
                date = parts[0]
            # Search any remaining parts for a time-ish token with ':' or 'AM/PM'
            for p in parts[1:]:
                s = p.replace("–", "-")  # normalize en dash
                if ":" in s or "am" in s.lower() or "pm" in s.lower():
                    time = p
                    break
        entry = {
            "name": name,
            "number": number,
            "date": date,
            "time": time,
            "crn": current_crn,
            "section": current_section,
            "kind": kind,
        }
        data[list_name].append(entry)

    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        low = ln.lower()

        # Section headers / state switches
        if ln.startswith("Lecture Exams"):
            in_lecture_exams, in_lab_exams = True, False
            i += 1
            continue
        if ln.startswith("Lab Exams"):
            in_lab_exams, in_lecture_exams = True, False
            i += 1
            continue
        if ln.startswith("Office Hours"):
            in_office_hours = True
            # Capture the following non-empty lines until a blank or next header
            block: List[str] = []
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if not s:
                    break
                # stop if we encounter another top-level header
                if s.endswith(":") and s[:-1].istitle():
                    break
                block.append(lines[j].strip())
                j += 1
            data["office_hours"] = " 
".join(block) if block else ln
            i = j
            continue

        # CRN line examples:
        #  "CRN 70868 (Tue lec)" or "CRN 70865 (Wed lec)"
        if ln.startswith("CRN "):
            # Grab first token after CRN and optional parentheses part
            # e.g., "CRN 70868 (Tue lec)" -> crn="70868", section="Tue lec"
            try:
                tokens = ln.split()
                current_crn = tokens[1]
            except Exception:
                current_crn = None
            # Parentheses content, if present
            if "(" in ln and ")" in ln:
                current_section = ln.split("(", 1)[1].rsplit(")", 1)[0].strip()
            else:
                current_section = None
            i += 1
            continue

        # Capture Late/Quizzes/Important Dates/Due lines simply
        if low.startswith("policies") and "late" in low:
            data["late_policy"] = ln
            i += 1
            continue
        if low.startswith("quizzes"):
            data["quizzes_policy"] = ln
            i += 1
            continue
        if "due" in low:
            data["due_lines"].append(ln)
            i += 1
            continue

        # Within exam sections, capture items
        if in_lecture_exams and (low.startswith("exam ") or low.startswith("final exam")):
            push_exam(ln, "exams", kind="exam")
            i += 1
            continue
        if in_lab_exams:
            # Typical lab exam lines look like: "Lab Exam 1 — Intro: 8/20"
            if low.startswith("lab exam"):
                push_exam(ln.replace(" — ", ": "), "lab_practicals", kind="practical")
                i += 1
                continue

        i += 1

    return data


# ---------------------- Deterministic answering -------------------------------

def _answer_from_indexed_logistics(q: str) -> Optional[str]:
    blocks = st.session_state.get("bio205_logistics_blocks") or []
    if not blocks:
        return None

    ql = q.lower().strip()

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
        return "- " + " ".join(bits) + f"  
[Source: {src}]"

    # detect number if present
    num = None
    for token in ql.replace("?", "").split():
        if token.isdigit():
            num = token
            break

    # If the question mentions exam/practical, list matching entries
    if any(k in ql for k in ("exam", "midterm", "test", "practical")):
        lines: List[str] = []
        for block in blocks:
            src = block.get("source", "bio205_logistics.md")
            for e in (block.get("exams", []) + block.get("lab_practicals", [])):
                if num and e.get("number") != num:
                    continue
                if not num and not (e.get("date") or e.get("time")):
                    continue
                lines.append(fmt(e, src))
        if lines:
            title = f"**{('Exam ' + num) if num else 'Exams/Practicals'}**"
            return title + "
" + "
".join(lines)

    # Office hours
    if "office hour" in ql or "office-hours" in ql:
        for block in blocks:
            if block.get("office_hours"):
                return f"**Office Hours**  
{block['office_hours']}  
[Source: {block.get('source','bio205_logistics.md')}]"

    # Late policy
    if "late policy" in ql or "late work" in ql or ("late" in ql and "policy" in ql):
        for block in blocks:
            if block.get("late_policy"):
                return f"**Late Policy**  
{block['late_policy']}  
[Source: {block.get('source','bio205_logistics.md')}]"

    # Quizzes
    if "quiz" in ql or "quizzes" in ql:
        for block in blocks:
            if block.get("quizzes_policy"):
                return f"**Quizzes**  
{block['quizzes_policy']}  
[Source: {block.get('source','bio205_logistics.md')}]"

    # Generic due lines
    if "due" in ql:
        lines = []
        for block in blocks:
            for ln in block.get("due_lines", []):
                lines.append(f"- {ln}  
[Source: {block.get('source','bio205_logistics.md')}]")
        if lines:
            return "**Due items found in syllabus**
" + "
".join(lines)

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

    # Ensure logistics are loaded from secrets → file → memory once per session
    _ensure_logistics_loaded_once()

    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Set OPENAI_API_KEY to enable live answers.")

    # Minimal sidebar
    if show_sidebar_controls:
        st.sidebar.subheader("BIO 205 Tutor")
        mode = st.sidebar.radio("Mode", ["Explainer", "Quizzer"], index=1)
        temperature = st.sidebar.slider("Creativity", 0.0, 1.0, 0.4)
        if st.sidebar.button("🔄 Reindex logistics"):
            # Reset the flag to force re-read from disk
            st.session_state.pop("bio205_logistics_indexed", None)
            _ensure_logistics_loaded_once()
            blocks = st.session_state.get("bio205_logistics_blocks") or []
            exams = sum(len(b.get("exams", [])) for b in blocks)
            pracs = sum(len(b.get("lab_practicals", [])) for b in blocks)
            st.sidebar.success(f"Reindexed. Found {exams} exams, {pracs} practicals.")
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
    direct = _answer_from_indexed_logistics(user_text)
    if direct:
        with st.chat_message("assistant"):
            st.markdown(direct)
        st.session_state.bio205_chat.append({"role": "assistant", "content": direct})
        return

    # 2) Otherwise, normal model chat (no retrieval)
    dev = (
        f"Mode: {mode}. {_mode_instruction(mode)}
"
        f"Course: {course_hint}
"
        f"When answering logistics/objectives, prefer and cite 'bio205_logistics.md'."
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
