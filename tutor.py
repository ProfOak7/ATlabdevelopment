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
EMBED_MODEL   = os.getenv("BIO205_EMBED_MODEL", "text-embedding-3-large")

SYSTEM_PROMPT = """You are BIO 205 Tutor for Human Anatomy at Cuesta College.
Be concise, friendly, and accurate. Prefer Socratic guidance (ask one quick
question before explaining when appropriate). NEVER reveal answer keys; give hints
instead. When you use course knowledge, append [Source: <filename>]."""

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
    r"(?:,\s*\d{4})?\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b)"
)
_TIME_PAT = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?(?:\s*-\s*\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)?\b")
_EXAM_PAT = re.compile(r"\b(Exam|Midterm|Test|Practical)\s*\d*\b", re.I)
_OFFICE_PAT = re.compile(r"office\s*hours", re.I)
_LATE_PAT = re.compile(r"\blate\s*policy|\blate\s+work", re.I)
_QUIZ_PAT = re.compile(r"\bquiz|quizzes\b", re.I)
_DUE_PAT = re.compile(r"\bdue\b", re.I)
_POLICY_PAT = re.compile(r"\bpolicy\b", re.I)

def _extract_logistics_from_text(text: str, source_name: str) -> dict:
    data = {
        "source": source_name,
        "exams": [],
        "lab_practicals": [],
        "office_hours": None,
        "late_policy": None,
        "quizzes_policy": None,
        "due_lines": []
    }
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if _EXAM_PAT.search(ln):
            name = _EXAM_PAT.search(ln).group(0)
            date = _DATE_PAT.search(ln)
            time = _TIME_PAT.search(ln)
            entry = {
                "name": name,
                "date": date.group(0) if date else None,
                "time": time.group(0) if time else None,
                "line": ln
            }
            if "practical" in name.lower():
                data["lab_practicals"].append(entry)
            else:
                data["exams"].append(entry)
            continue
        if _OFFICE_PAT.search(ln) and not data["office_hours"]:
            data["office_hours"] = ln
            continue
        if (_LATE_PAT.search(ln) or ("late" in ln.lower() and _POLICY_PAT.search(ln))) and not data["late_policy"]:
            data["late_policy"] = ln
            continue
        if _QUIZ_PAT.search(ln) and "policy" in ln.lower() and not data["quizzes_policy"]:
            data["quizzes_policy"] = ln
            continue
        if _DUE_PAT.search(ln):
            data["due_lines"].append(ln)
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
    ql = q.lower()
    parts = []

    if any(k in ql for k in ["exam", "midterm", "test", "practical"]):
        for block in info:
            src = block["source"]
            for e in block.get("exams", []):
                line = f"- {e['name']}"
                if e.get("date"): line += f": {e['date']}"
                if e.get("time"): line += f" {e['time']}"
                line += f"  \n[Source: {src}]"
                parts.append(line)
            for p in block.get("lab_practicals", []):
                line = f"- {p['name']}"
                if p.get("date"): line += f": {p['date']}"
                if p.get("time"): line += f" {p['time']}"
                line += f"  \n[Source: {src}]"
                parts.append(line)
        if parts:
            return "**Exams/Practicals**\n" + "\n".join(parts)

    if "office hour" in ql or "office-hours" in ql:
        for block in info:
            if block.get("office_hours"):
                return f"**Office Hours**  \n{block['office_hours']}  \n[Source: {block['source']}]"

    if "late policy" in ql or "late work" in ql or ("late" in ql and "policy" in ql):
        for block in info:
            if block.get("late_policy"):
                return f"**Late Policy**  \n{block['late_policy']}  \n[Source: {block['source']}]"

    if "quiz" in ql or "quizzes" in ql:
        for block in info:
            if block.get("quizzes_policy"):
                return f"**Quizzes**  \n{block['quizzes_policy']}  \n[Source: {block['source']}]"

    if "due" in ql:
        for block in info:
            if block.get("due_lines"):
                return "**Due items found in syllabus**\n" + \
                       "\n".join(f"- {ln}  \n[Source: {block['source']}]" for ln in block["due_lines"])
    return None

# ------------- Retrieval helpers -------------

def _read_knowledge(knowledge_dir: str) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    base = pathlib.Path(knowledge_dir)
    if not base.exists():
        return docs
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}:
            text = p.read_text(encoding="utf-8", errors="ignore")
            # chunk (with no overlap, simple)
            for i in range(0, len(text), 1200):
                docs.append({"filename": p.name, "text": text[i:i+1200]})
    return docs

def _embed_texts(client: OpenAI, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    emb = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [e.embedding for e in emb.data]

def init_tutor(knowledge_dir: Optional[str]) -> None:
    """Call once (e.g., at app start). Builds an in-memory index if knowledge_dir is provided."""
    if "bio205_index_ready" in st.session_state:
        return
    st.session_state.bio205_index_ready = True
    st.session_state.bio205_index = None
    st.session_state.bio205_docs = None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not knowledge_dir:
        return
    client = OpenAI(api_key=api_key)

    docs = _read_knowledge(knowledge_dir)
    if not docs:
        return

    import numpy as np
    vecs = _embed_texts(client, [d["text"] for d in docs])
    if not vecs:
        return
    V = np.array(vecs, dtype="float32")
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-12)

    st.session_state.bio205_docs = docs
    st.session_state.bio205_index = V  # vectors aligned with docs

def _retrieve(query: str, k: int = 4) -> List[Dict[str, Any]]:
    if st.session_state.get("bio205_index") is None or st.session_state.get("bio205_docs") is None:
        return []
    import numpy as np
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []
    client = OpenAI(api_key=api_key)
    qv = _embed_texts(client, [query])[0]
    qv = qv / (np.linalg.norm(qv) + 1e-12)
    sims = st.session_state.bio205_index @ qv
    topk = sims.argsort()[-k:][::-1]
    out = []
    for i in topk:
        d = st.session_state.bio205_docs[int(i)]
        out.append({"filename": d["filename"], "text": d["text"], "score": float(sims[int(i)])})
    return out

# ------------- Public UI -------------

def render_chat(
    course_hint: str = "BIO 205: Human Anatomy",
    knowledge_enabled: bool = False,   # True if you passed a real knowledge_dir to init_tutor()
    show_sidebar_controls: bool = True,
) -> None:
    """Renders a chat panel. Call this from your page (main or a tab)."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Set OPENAI_API_KEY to enable live answers.")

    if show_sidebar_controls:
        st.sidebar.subheader("BIO 205 Tutor")
        mode = st.sidebar.radio("Mode", ["Coach", "Explainer", "Quizzer", "Editor"], index=0)
        use_retrieval = st.sidebar.checkbox("Use course knowledge", value=knowledge_enabled)
        temperature = st.sidebar.slider("Creativity", 0.0, 1.0, 0.4)
        if st.sidebar.button("🔄 Reindex knowledge"):
            st.session_state.pop("bio205_index_ready", None)
            st.session_state.pop("bio205_index", None)
            st.session_state.pop("bio205_docs", None)
            # Rebuild index and logistics
            if st.session_state.get("bio205_knowledge_dir"):
                init_tutor(st.session_state["bio205_knowledge_dir"])
                _load_and_index_logistics(st.session_state["bio205_knowledge_dir"])
            st.sidebar.success("Reindexed.")

    else:
        mode, use_retrieval, temperature = "Coach", knowledge_enabled, 0.4

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

    user_text = st.chat_input("Ask about BIO 205 (e.g., 'How do AV valves differ from semilunar valves?')")
    if not user_text:
        return

    # Echo user
    st.session_state.bio205_chat.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # --- Deterministic logistics answers FIRST ---
    direct = _answer_from_indexed_logistics(user_text)
    if direct:
        with st.chat_message("assistant"):
            st.markdown(direct)
        st.session_state.bio205_chat.append({"role": "assistant", "content": direct})
        return

    # Otherwise, proceed with model + (optional) retrieval
    dev = f"Mode: {mode}. {_mode_instruction(mode)}\nCourse: {course_hint}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "developer", "content": dev}]

    # Keep last ~8 turns for cost control
    short_hist = [m for m in st.session_state.bio205_chat if m["role"] in ("user", "assistant")][-8:]
    messages.extend(short_hist)

    # Attach retrieval snippets if enabled
    if client and use_retrieval:
        hits = _retrieve(user_text, k=8)
        # Prefer syllabus chunks
        hits.sort(key=lambda h: 0 if "syllabus" in h["filename"].lower() else 1)
        hits = hits[:4]
        if hits:
            kb = []
            for h in hits:
                kb.append(f"[Source: {h['filename']}]\n{h['text']}")
            messages.append({
                "role": "developer",
                "content": "Use the following course knowledge and cite as [Source: <filename>]:\n\n" + "\n\n---\n\n".join(kb)
            })

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
