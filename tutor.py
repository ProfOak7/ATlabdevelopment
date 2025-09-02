# tutor.py
import os
import pathlib
from typing import List, Dict, Any, Optional

import streamlit as st
from openai import OpenAI

DEFAULT_MODEL = os.getenv("BIO212_TUTOR_MODEL", "gpt-4o-mini")
EMBED_MODEL   = os.getenv("BIO212_EMBED_MODEL", "text-embedding-3-large")

SYSTEM_PROMPT = """You are BIO 212 Tutor for Human Biology at Cuesta College.
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
    if "bio212_index_ready" in st.session_state:
        return
    st.session_state.bio212_index_ready = True
    st.session_state.bio212_index = None
    st.session_state.bio212_docs = None

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

    st.session_state.bio212_docs = docs
    st.session_state.bio212_index = V  # vectors aligned with docs

def _retrieve(query: str, k: int = 4) -> List[Dict[str, Any]]:
    if st.session_state.get("bio212_index") is None or st.session_state.get("bio212_docs") is None:
        return []
    import numpy as np
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []
    client = OpenAI(api_key=api_key)
    qv = _embed_texts(client, [query])[0]
    qv = qv / (np.linalg.norm(qv) + 1e-12)
    sims = st.session_state.bio212_index @ qv
    topk = sims.argsort()[-k:][::-1]
    out = []
    for i in topk:
        d = st.session_state.bio212_docs[int(i)]
        out.append({"filename": d["filename"], "text": d["text"], "score": float(sims[int(i)])})
    return out

# ---------- Public UI ----------

def render_chat(
    course_hint: str = "BIO 212: Human Biology",
    knowledge_enabled: bool = False,   # True if you passed a real knowledge_dir to init_tutor()
    show_sidebar_controls: bool = True,
) -> None:
    """Renders a chat panel. Call this from your page (main or a tab)."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Set OPENAI_API_KEY to enable live answers.")

    if show_sidebar_controls:
        st.sidebar.subheader("BIO 212 Tutor")
        mode = st.sidebar.radio("Mode", ["Coach", "Explainer", "Quizzer", "Editor"], index=0)
        use_retrieval = st.sidebar.checkbox("Use course knowledge", value=knowledge_enabled)
        temperature = st.sidebar.slider("Creativity", 0.0, 1.0, 0.4)
    else:
        mode, use_retrieval, temperature = "Coach", knowledge_enabled, 0.4

    if "bio212_chat" not in st.session_state:
        st.session_state.bio212_chat = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Show prior turns
    for m in st.session_state.bio212_chat:
        if m["role"] == "user":
            with st.chat_message("user"):
                st.markdown(m["content"])
        elif m["role"] == "assistant":
            with st.chat_message("assistant"):
                st.markdown(m["content"])

    user_text = st.chat_input("Ask about BIO 212 (e.g., 'Why is the heart a double pump?')")
    if not user_text:
        return

    # Echo user
    st.session_state.bio212_chat.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    dev = f"Mode: {mode}. {_mode_instruction(mode)}\nCourse: {course_hint}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "developer", "content": dev}]

    # Keep last ~8 turns for cost control
    short_hist = [m for m in st.session_state.bio212_chat if m["role"] in ("user", "assistant")][-8:]
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
        st.session_state.bio212_chat.append({"role": "assistant", "content": reply})
