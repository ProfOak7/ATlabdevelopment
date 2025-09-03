# tutor.py  — BIO 205 (Human Anatomy)

import os
import re
import json
import pathlib
from typing import List, Dict, Any, Optional

import streamlit as st
from openai import OpenAI

# Use BIO205-specific env vars; fall back to sensible defaults
DEFAULT_MODEL = os.getenv("BIO205_TUTOR_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT = """You are BIO 205 Tutor for Human Anatomy at Cuesta College.
Be concise, friendly, and accurate. Prefer Socratic guidance (ask one quick
question before explaining when appropriate). NEVER reveal answer keys; give hints
instead. When you use course knowledge, append [Source: <filename>].
For logistics or lab objectives, cite [Source: bio205_logistics.md] if information is present there."""


def _mode_instruction(mode: str) -> str:
    return {
        "Coach":    "Act as a Socratic coach. Ask brief, targeted questions; reveal hints progressively; check understanding.",
        "Explainer":"Explain clearly with analogies and a quick misconception check tied to everyday life.",
        "Quizzer":  "Ask 2–4 short questions, give immediate feedback, then a brief recap.",
        "Editor":   "Give formative, rubric-aligned feedback on short writing. Suggest 2–3 concrete edits.",
    }.get(mode, "Explain clearly and check understanding briefly.")

# ------------- Logistics helpers (syllabus parsing) -------------

# Optional explicit list via env/Secrets:
# BIO205_LOGISTICS_FILES="BIO 205_Fall25_Syllabus_70865_Okerblom.txt;BIO 205_Fall25_Syllabus_70868_Okerblom.txt"
_LOGISTICS_FILELIST = os.getenv("BIO205_LOGISTICS_FILES", "").strip()

def _is_logistics_file(path: pathlib.Path) -> bool:
    if _LOGISTICS_FILELIST:
        wanted = {n.strip().lower() for n in _LOGISTICS_FILELIST.split(";") if n.strip()}
        return path.name.lower() in wanted
    return "syllabus" in path.name.lower()

_DATE_PAT = re.compile(
    r"(?:\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}"
    r"(?:,\s*\d{4})?\b"                              # e.g., Sep 9 or Sep 9, 2025
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"            # <-- allows 9/9 and 9/9/2025
    r"|\b\d{4}-\d{2}-\d{2}\b)"                      # ISO 2025-09-09
)
_TIME_PAT = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?(?:\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))?\b")
_EXAM_PAT = re.compile(r"\b(Exam|Midterm|Test|Practical)\s*\d*\b", re.I)
_OFFICE_PAT = re.compile(r"office\s*hours", re.I)
_LATE_PAT = re.compile(r"\blate\s*policy|\blate\s+work", re.I)
_QUIZ_PAT = re.compile(r"\bquiz|quizzes\b", re.I)
_DUE_PAT = re.compile(r"\bdue\b", re.I)
_POLICY_PAT = re.compile(r"\bpolicy\b", re.I)

def _extract_logistics_from_text(text: str, source_name: str) -> dict:
    """
    Parse syllabus-like text and pull structured logistics.
    Captures 'Exam N' / 'Practical N' and attaches the closest date/time.
    Handles tables flattened to text where a date is on its own line
    (e.g., a line '9/9' followed by '***Lecture Exam 1***').
    """
    data = {
        "source": source_name,
        "exams": [],           # {name, number, date?, time?, line}
        "lab_practicals": [],  # same
        "office_hours": None,
        "late_policy": None,
        "quizzes_policy": None,
        "due_lines": []
    }

    # Keep originals for output, and a stripped copy for matching
    raw_lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln.strip() for ln in raw_lines]

    # Standalone date rows we should "carry forward" to the next content row
    date_row_pat = re.compile(
        r"^\s*(?:"
        r"(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?)"                 # 9/9 or 9/9/2025
        r"|(?:\d{4}-\d{2}-\d{2})"                           # 2025-09-09
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?"
        r")\s*$", re.I
    )
    current_date = None

    def nearest_time(i: int, win: int = 2) -> Optional[str]:
        idxs = [i] + [j for k in range(1, win+1) for j in (i-k, i+k) if 0 <= j < len(lines)]
        for j in idxs:
            t = _TIME_PAT.search(lines[j])
            if t:
                return t.group(0)
        return None

    # Dedupe map: (kind, number) -> best entry
    seen: Dict[tuple, Dict[str, Any]] = {}

    for i, ln in enumerate(lines):
        if not ln:
            continue

        # If this line is just a date, remember it for the next row and move on
        if date_row_pat.match(ln):
            current_date = ln
            continue

        # Office hours / policies (first occurrence only)
        if _OFFICE_PAT.search(ln) and not data["office_hours"]:
            data["office_hours"] = raw_lines[i].strip()
        if (_LATE_PAT.search(ln) or ("late" in ln.lower() and _POLICY_PAT.search(ln))) and not data["late_policy"]:
            data["late_policy"] = raw_lines[i].strip()
        if _QUIZ_PAT.search(ln) and "policy" in ln.lower() and not data["quizzes_policy"]:
            data["quizzes_policy"] = raw_lines[i].strip()
        if _DUE_PAT.search(ln):
            data["due_lines"].append(raw_lines[i].strip())

        # Exams / Practicals
        m = _EXAM_PAT.search(ln)
        if not m:
            continue

        label = m.group(0)  # e.g., "Exam 1", "Practical 1", "Exam"
        num_match = re.search(r"(?:Exam|Midterm|Test|Practical)\s*(\d+)", label, re.I)
        number = num_match.group(1) if num_match else None

        # If it's just "Exam" with no number AND no nearby date, skip (reduces noise)
        if not number and not _DATE_PAT.search(ln):
            if not current_date:
                continue

        # Prefer a carried-forward date; otherwise look for an inline date on this line
        date_str = current_date or (_DATE_PAT.search(ln).group(0) if _DATE_PAT.search(ln) else None)
        time_str = nearest_time(i, win=2)

        kind = "practical" if "practical" in label.lower() else "exam"
        dedupe_key = (kind, number or raw_lines[i].strip().lower())
        nice_name = (("Practical " if kind == "practical" else "Exam ") + (number if number else "")).strip()

        entry = {
            "name": nice_name if number or kind == "practical" else label.strip(),
            "number": number,
            "date": date_str,
            "time": time_str,
            "line": raw_lines[i].strip()
        }

        # Prefer entries that actually have a date
        if dedupe_key not in seen or (date_str and not seen[dedupe_key].get("date")):
            seen[dedupe_key] = entry

    # Move from map to lists
    for (kind, _), entry in seen.items():
        if kind == "practical":
            data["lab_practicals"].append(entry)
        else:
            data["exams"].append(entry)

    # Sort numerically when possible (Exam 1, Exam 2, …)
    def _num_key(e):
        try:
            return int(e["number"]) if e.get("number") else 999
        except Exception:
            return 999

    data["exams"].sort(key=_num_key)
    data["lab_practicals"].sort(key=_num_key)
    return data

def _load_and_index_logistics(knowledge_dir: Optional[str]) -> None:
    """Scan knowledge_dir for syllabus files, extract logistics, and cache them."""
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
        if p.suffix.lower() not in {".txt", ".md"}:
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
        # Optional: prefer a selected section if you store one in session
        sec = st.session_state.get("bio205_section")
        if sec:
            collected.sort(key=lambda b: 0 if sec in b.get("source","") else 1)
        st.session_state.bio205_logistics = collected

def _answer_from_indexed_logistics(q: str) -> Optional[str]:
    """Answer logistics Qs deterministically from cached syllabus extracts."""
    info = st.session_state.get("bio205_logistics")
    if not info:
        return None

    ql = q.lower().strip()

    # Prefer selected section, if present
    sec = st.session_state.get("bio205_section")
    if sec:
        info = sorted(info, key=lambda b: 0 if sec in b.get("source","") else 1)

    # Try to detect a specific exam/practical number in the question
    num = None
    mnum = re.search(r"(?:exam|practical)\s*(\d+)", ql, re.I)
    if mnum:
        num = mnum.group(1)

    # Build response lines
    def fmt(entry, src):
        bits = [entry["name"]]
        if entry.get("date"):
            bits.append(entry["date"])
        if entry.get("time"):
            bits.append(entry["time"])
        return "- " + " ".join(bits) + f"  \n[Source: {src}]"

    # Exams / Practicals only if the question is about them or generically about 'exam/test'
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

    # Quizzes
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

# ------------- Public UI -------------

def render_chat(
    course_hint: str = "BIO 205: Human Anatomy",
    knowledge_enabled: bool = False,   # legacy; ignored now
    show_sidebar_controls: bool = True,
) -> None:
    """Renders a chat panel. Deterministic logistics first; otherwise model-only."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Set OPENAI_API_KEY to enable live answers.")

    if show_sidebar_controls:
        st.sidebar.subheader("BIO 205 Tutor")
        mode = st.sidebar.radio("Mode", ["Coach", "Explainer", "Quizzer", "Editor"], index=0)
        temperature = st.sidebar.slider("Creativity", 0.0, 1.0, 0.4)
        if st.sidebar.button("🔄 Reindex knowledge"):
            # Just reload logistics (no embeddings)
            if st.session_state.get("bio205_knowledge_dir"):
                _load_and_index_logistics(st.session_state["bio205_knowledge_dir"])
            st.sidebar.success("Reindexed.")
    else:
        mode, temperature = "Coach", 0.4

    if "bio205_chat" not in st.session_state:
        st.session_state.bio205_chat = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Show prior turns
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
    dev = f"Mode: {mode}. {_mode_instruction(mode)}\nCourse: {course_hint}\n" \
          f"When answering logistics/objectives, prefer and cite 'bio205_logistics.md'."
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "developer", "content": dev}]

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


