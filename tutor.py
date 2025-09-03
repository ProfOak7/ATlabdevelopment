# tutor.py  — BIO 205 (Human Anatomy)

import os
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
        st.session_state.bio205_logistics = collected

def _answer_from_indexed_logistics(q: str) -> Optional[str]:
    """Answer logistics Qs deterministically from cached syllabus extracts."""
    info = st.session_state.get("bio205_logistics")
    if not info:
        return None
    ql = q.lower()
    parts = []

    # Exams & Practicals
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
        for block in info:
            if block.get("due_lines"):
                return "**Due items found in syllabus**\n" + \
                       "\n".join(f"- {ln}  \n[Source: {block['source']}]" for ln in block["due_lines"])

    return None
# ---------- Retrieval helpers (optional) ----------
def _read_knowledge(knowledge_dir: str) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    base = pathlib.Path(knowledge_dir)
    if not base.exists():
        return docs
    for p in base.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for i in range(0, len(text), 1200):  # ~1200-char chunks
                docs.append({"filename": p.name, "text": text[i:i+1200]})
    return docs

def _embed_texts(client: OpenAI, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    emb = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [e.embedding for e in emb.data]

def init_tutor(knowledge_dir: Optional[str]) -> None:
    """
    Call once (e.g., at app start). Builds an in-memory index if knowledge_dir is provided.
    """
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

# ---------- Public UI ----------

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

    dev = f"Mode: {mode}. {_mode_instruction(mode)}\nCourse: {course_hint}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "developer", "content": dev}]

    # Keep last ~8 turns for cost control
    short_hist = [m for m in st.session_state.bio205_chat if m["role"] in ("user", "assistant")][-8:]
    messages.extend(short_hist)

    # Attach retrieval snippets if enabled
    if client and use_retrieval:
        hits = _retrieve(user_text, k=4)
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
