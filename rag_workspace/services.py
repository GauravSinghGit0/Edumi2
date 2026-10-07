"""
rag_workspace/services.py
Dedicated Service Layer for AI Study Workspace RAG Engine.
Handles document chunk retrieval with nomic-embed-text vector embeddings,
Cloudflare / Ollama LLM execution, prompt formatting, user session history,
and 5 specialized educational modes (Ask, Explain, Summarize, Practice/Quiz, Study/Revision).
"""

import json
import re
import math
import requests
from django.utils import timezone
from meetings.models import StudyMaterial, MaterialChunk
from .models import RagSession, RagChatMessage, RagQueryLog, RagInstructorSetting
import os
from django.conf import settings

# LLM & Embedding Endpoints Configuration (Loaded dynamically from .env via Django settings)
def get_ai_config():
    return {
        'llm_url': getattr(settings, 'AI_LLM_URL', os.environ.get('AI_LLM_URL', '')),
        'bearer_token': getattr(settings, 'AI_LLM_BEARER_TOKEN', os.environ.get('AI_LLM_BEARER_TOKEN', '')),
        'model_name': getattr(settings, 'AI_MODEL_NAME', os.environ.get('AI_MODEL_NAME', 'phi:latest')),
        'embedding_url': getattr(settings, 'AI_EMBEDDING_URL', os.environ.get('AI_EMBEDDING_URL', 'http://127.0.0.1:11434')),
        'embedding_model': getattr(settings, 'AI_EMBEDDING_MODEL', os.environ.get('AI_EMBEDDING_MODEL', 'nomic-embed-text:latest')),
        'openai_api_key': getattr(settings, 'OPENAI_API_KEY', os.environ.get('OPENAI_API_KEY', '')),
        'openai_model': getattr(settings, 'OPENAI_MODEL', os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')),
    }


import time

_EMBEDDING_OFFLINE_UNTIL = 0.0


def get_nomic_embedding(text):
    """
    Generates dense float vector embedding using embedding model on Ollama server or OpenAI fallback.
    Uses a 30s circuit breaker if service is offline to prevent batch indexing timeouts.
    """
    global _EMBEDDING_OFFLINE_UNTIL
    if not text or not text.strip():
        return None

    now = time.time()
    if now < _EMBEDDING_OFFLINE_UNTIL:
        return None

    cfg = get_ai_config()

    # 1. Try Ollama local / remote embeddings
    if cfg['embedding_url']:
        url = f"{cfg['embedding_url'].rstrip('/')}/api/embeddings"
        payload = {
            "model": cfg['embedding_model'],
            "prompt": text[:2000]
        }
        try:
            res = requests.post(url, json=payload, timeout=1.5)
            if res.status_code == 200:
                data = res.json()
                if data.get('embedding'):
                    return data.get('embedding')
        except Exception:
            pass

    # 2. Try OpenAI API Embeddings if key configured
    if cfg['openai_api_key']:
        try:
            res = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {cfg['openai_api_key']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "text-embedding-3-small",
                    "input": text[:2000]
                },
                timeout=2.0
            )
            if res.status_code == 200:
                data = res.json()
                return data['data'][0]['embedding']
        except Exception:
            pass

    _EMBEDDING_OFFLINE_UNTIL = now + 30.0
    return None


def cosine_similarity(v1, v2):
    """Calculates cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rewrite_query(prompt):
    """
    Cleans and normalizes user query by removing conversational prefixes/filler words,
    extra whitespace, and non-essential punctuation for vector and lexical retrieval.
    """
    if not prompt:
        return ""
    cleaned = prompt.strip()
    patterns = [
        r'^(hey|hi|hello|please|can you|could you|bhai|batao|tell me|explain|describe|what is|who is|where is|how does|why is|what are|tell me about)\s+',
    ]
    lowered = cleaned.lower()
    for pat in patterns:
        lowered = re.sub(pat, '', lowered, flags=re.IGNORECASE)
    cleaned_words = re.sub(r'[^\w\s]', ' ', lowered)
    normalized = re.sub(r'\s+', ' ', cleaned_words).strip()
    return normalized if normalized else prompt


def rerank_and_deduplicate_chunks(chunks, min_score=0.15, max_chunks=6):
    """
    Reranks retrieved chunks by relevance score, filters out chunks below min_score threshold (0.15),
    and deduplicates identical or heavily overlapping context snippets before sending to LLM.
    """
    if not chunks:
        return []

    sorted_chunks = sorted(chunks, key=lambda x: x['score'], reverse=True)

    filtered = []
    seen_texts = []

    for c in sorted_chunks:
        if c['score'] < min_score:
            continue
        text_snippet = c['text'].strip().lower()
        
        is_dup = False
        for seen in seen_texts:
            if text_snippet in seen or seen in text_snippet:
                is_dup = True
                break
            words_a = set(text_snippet.split())
            words_b = set(seen.split())
            if words_a and words_b:
                overlap = len(words_a.intersection(words_b)) / float(min(len(words_a), len(words_b)))
                if overlap > 0.85:
                    is_dup = True
                    break
        if not is_dup:
            seen_texts.append(text_snippet)
            filtered.append(c)
            if len(filtered) >= max_chunks:
                break

    return filtered


def retrieve_source_chunks(material_ids, query, top_k=10):
    """
    Retrieves and ranks relevant text chunks using Metadata Filtering + Hybrid Search:
    Combines nomic-embed-text Cosine Vector Similarity (75% weight) with BM25 Keyword Matching (25% weight).
    Metadata filtering by material_ids and is_published=True.
    """
    if not material_ids:
        return []

    # Metadata filtering at Database layer
    chunks = MaterialChunk.objects.filter(
        material_id__in=material_ids,
        material__is_published=True
    ).select_related('material', 'material__unit')

    if not chunks.exists():
        return []

    rewritten_query = rewrite_query(query)
    effective_query = rewritten_query if rewritten_query else query

    # Get query embedding for semantic search
    query_vec = get_nomic_embedding(effective_query) if effective_query else None

    query_clean = re.sub(r'[^\w\s]', '', (effective_query or '').lower())
    query_tokens = [w for w in query_clean.split() if len(w) > 2]

    scored = []
    for chunk in chunks:
        c_text = chunk.chunk_text.lower()
        m_title = chunk.material.title.lower()

        # 1. Keyword Score
        kw_score = 0.0
        matches = 0
        for token in query_tokens:
            cnt = c_text.count(token)
            if cnt > 0:
                kw_score += (1.0 + math.log(cnt))
                matches += 1
            if token in m_title:
                kw_score += 2.5

        if query_tokens and matches > 0:
            kw_norm = kw_score / (len(query_tokens) ** 0.5)
        else:
            kw_norm = 0.0

        # 2. Semantic Embedding Vector Similarity
        sem_sim = 0.0
        chunk_vec = chunk.embedding_vector
        if not chunk_vec and query_vec:
            chunk_vec = get_nomic_embedding(chunk.chunk_text[:1500])
            if chunk_vec:
                try:
                    chunk.embedding_vector = chunk_vec
                    chunk.save(update_fields=['embedding_vector'])
                except Exception:
                    pass

        if query_vec and chunk_vec:
            sem_sim = cosine_similarity(query_vec, chunk_vec)

        # 3. Hybrid Combined Score (75% Vector Embedding + 25% BM25 Lexical Keyword)
        if query_vec and chunk_vec:
            final_score = (0.75 * sem_sim) + (0.25 * min(1.0, kw_norm / 5.0))
        elif query_tokens:
            final_score = kw_norm
        else:
            final_score = 1.0 / (chunk.chunk_index + 1)

        page_num = chunk.page_number or (chunk.chunk_index + 1)
        unit_title = chunk.material.unit.title if chunk.material.unit else "General"
        scored.append({
            'chunk_id': chunk.id,
            'material_id': chunk.material.id,
            'material_title': chunk.material.title,
            'unit_title': unit_title,
            'page_number': page_num,
            'chunk_index': chunk.chunk_index,
            'text': chunk.chunk_text,
            'score': final_score,
            'file_url': chunk.material.file.url if chunk.material.file else None,
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_k]


def call_phi_llm(prompt, system_prompt=""):
    """Calls Cloudflare / Ollama API hosting phi:latest model with streaming payload aggregation."""
    return "".join(list(call_phi_llm_stream(prompt, system_prompt=system_prompt))) or None


def call_phi_llm_stream(prompt, system_prompt=""):
    """
    Generator that yields individual text tokens as they arrive from streaming API.
    Supports Cloudflare Tunnels, Ollama native generate API, and OpenAI ChatCompletions.
    """
    cfg = get_ai_config()
    headers = {
        'Authorization': f"Bearer {cfg['bearer_token']}",
        'Content-Type': 'application/json'
    }

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    payload = {
        'model': cfg['model_name'],
        'prompt': full_prompt,
        'stream': True
    }

    # Helper function to parse delta text from line
    def extract_text_from_line(line_str):
        if line_str.startswith('data:'):
            line_str = line_str[5:].strip()
        if not line_str or line_str == '[DONE]':
            return None, True
        try:
            data = json.loads(line_str)
            # Ollama format
            if 'response' in data:
                return data['response'], data.get('done', False)
            # OpenAI format
            if 'choices' in data and len(data['choices']) > 0:
                delta = data['choices'][0].get('delta', {})
                content = delta.get('content', '')
                finish = data['choices'][0].get('finish_reason') is not None
                return content, finish
        except Exception:
            pass
        return None, False

    # 1. Try primary LLM Endpoint (Cloudflare / Custom endpoint)
    if cfg['llm_url']:
        try:
            response = requests.post(
                cfg['llm_url'],
                headers=headers,
                json=payload,
                stream=True,
                timeout=(4, 60)
            )

            if response.status_code == 200:
                emitted_any = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        line_str = line.decode('utf-8')
                        part, done = extract_text_from_line(line_str)
                        if part:
                            emitted_any = True
                            yield part
                        if done:
                            break
                    except Exception:
                        continue
                if emitted_any:
                    return
        except Exception as err:
            print(f"[RAG Workspace LLM Stream Error] {err}")

    # 2. Try local / remote Ollama generate API
    if cfg['embedding_url']:
        try:
            ollama_generate_url = f"{cfg['embedding_url'].rstrip('/')}/api/generate"
            ollama_payload = {
                "model": cfg['model_name'],
                "prompt": full_prompt,
                "stream": True
            }
            res = requests.post(ollama_generate_url, json=ollama_payload, stream=True, timeout=(3, 60))
            if res.status_code == 200:
                emitted_any = False
                for line in res.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode('utf-8'))
                        response_part = data.get('response', '')
                        if response_part:
                            emitted_any = True
                            yield response_part
                        if data.get('done', False):
                            break
                    except Exception:
                        continue
                if emitted_any:
                    return
        except Exception as err:
            print(f"[Ollama Fallback LLM Stream Error] {err}")

    # 3. Try OpenAI API directly if key is configured
    if cfg['openai_api_key']:
        try:
            openai_payload = {
                "model": cfg['openai_model'],
                "messages": [
                    {"role": "system", "content": system_prompt or "You are an AI study assistant."},
                    {"role": "user", "content": prompt}
                ],
                "stream": True
            }
            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['openai_api_key']}",
                    "Content-Type": "application/json"
                },
                json=openai_payload,
                stream=True,
                timeout=(5, 60)
            )
            if res.status_code == 200:
                for line in res.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode('utf-8')
                    part, done = extract_text_from_line(line_str)
                    if part:
                        yield part
                    if done:
                        break
                return
        except Exception as err:
            print(f"[OpenAI Fallback LLM Error] {err}")


def generate_session_title(prompt):
    """Generates a clean, readable ChatGPT-style session title from user prompt."""
    if not prompt or not prompt.strip():
        return "AI Study Session"
    cleaned = rewrite_query(prompt)
    if not cleaned:
        cleaned = prompt.strip()
    words = cleaned.split()
    if not words:
        return "AI Study Session"
    title_str = " ".join(words[:6]).capitalize()
    if len(title_str) > 36:
        title_str = title_str[:33] + "..."
    return title_str or "AI Study Session"


def get_or_create_rag_session(user, session_id, prompt, mode, strict_mode=True):
    """
    Fetches an existing user RAG session or creates a new single-session container.
    Guarantees all message turns in a continuous conversation are stored under the same session.
    """
    session = None
    if session_id:
        try:
            session = RagSession.objects.filter(id=int(session_id), user=user).first()
        except Exception:
            pass

    if not session and user.is_authenticated:
        session = RagSession.objects.create(
            user=user,
            title=generate_session_title(prompt),
            strict_mode=strict_mode,
            active_mode=mode
        )
    elif session:
        if session.title in ("AI Study Session", "New Chat", "New AI Study Session", "Untitled Session") and prompt:
            session.title = generate_session_title(prompt)
        session.active_mode = mode
        session.updated_at = timezone.now()
        session.save(update_fields=['title', 'active_mode', 'updated_at'])

    return session


def run_rag_workspace_pipeline(user, material_ids, prompt="", mode="ask", explain_level="detailed", strict_mode=True, allow_external=False, session_id=None):
    """
    Main synchronous entrypoint for processing user study requests in RAG AI Study Workspace.
    Strict True RAG: Query Rewriting -> Metadata Filtering -> Hybrid Search -> Relevance Reranking & Deduplication -> Grounded Generation with Citations.
    """
    session = get_or_create_rag_session(user, session_id, prompt, mode, strict_mode)
    s_id = session.id if session else None

    materials = StudyMaterial.objects.filter(id__in=material_ids, is_published=True)
    if not materials.exists():
        return {
            'status': 'error',
            'message': 'No study materials selected.',
            'not_found': True,
            'answer': 'Not found in the knowledge base.',
            'sources': [],
            'session_id': s_id
        }

    raw_chunks = retrieve_source_chunks(material_ids, prompt, top_k=10)
    chunks = rerank_and_deduplicate_chunks(raw_chunks, min_score=0.15, max_chunks=6)

    if not chunks:
        msg = "Not found in the knowledge base."
        s_id = log_rag_query(user, mode, prompt, msg, 0, [], strict_mode, True, s_id, material_ids)
        return {
            'status': 'success',
            'not_found': True,
            'answer': msg,
            'sources': [],
            'can_fallback_external': False,
            'mode': mode,
            'session_id': s_id
        }

    context_blocks = []
    unique_sources = []
    seen = set()

    for idx, c in enumerate(chunks, 1):
        context_blocks.append(f"--- SOURCE [{idx}]: {c['material_title']} (Page {c['page_number']}) ---\n{c['text']}")
        s_key = (c['material_id'], c['page_number'])
        if s_key not in seen:
            seen.add(s_key)
            unique_sources.append({
                'material_id': c['material_id'],
                'title': c['material_title'],
                'unit_title': c['unit_title'],
                'page_number': c['page_number'],
                'file_url': c['file_url'],
                'snippet': c['text'][:140] + '...' if len(c['text']) > 140 else c['text']
            })

    context_str = "\n\n".join(context_blocks)

    # Multi-turn conversation context from existing session
    history_str = ""
    if session:
        prev_msgs = list(session.messages.order_by('-created_at')[:6])
        prev_msgs.reverse()
        if prev_msgs:
            h_lines = [f"{'Student' if m.role == 'user' else 'Assistant'}: {m.content}" for m in prev_msgs]
            history_str = "\n".join(h_lines)

    system_p = (
        "You are a strict Retrieval-Augmented Generation (RAG) system.\n"
        "Your ONLY task is to answer the user request based STRICTLY and ONLY on the provided RETRIEVED CONTEXT snippets below.\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. Answer ONLY using the facts present in the provided context. Do NOT use any external knowledge, assumptions, or prior training data.\n"
        "2. If the context does not contain sufficient facts to answer the user prompt completely, reply with EXACTLY: Not found in the knowledge base.\n"
        "3. For every statement or claim in your response, provide an inline citation in the format [Document Title, Page X].\n"
        "4. Keep your answer precise, grounded, deterministic, and traceable to the retrieved source chunks."
    )
    
    if history_str:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nRECENT CHAT HISTORY:\n{history_str}\n\nSTUDENT PROMPT: {prompt or 'Summarize key points from these chunks.'}"
    else:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nUSER PROMPT: {prompt or 'Summarize key points from these chunks.'}"

    answer = call_phi_llm(user_p, system_p)
    if not answer or "not found in the knowledge base" in answer.lower() or answer.strip() == "":
        answer = "Not found in the knowledge base."

    s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, s_id, material_ids)
    return {
        'status': 'success',
        'mode': mode,
        'answer': answer,
        'sources': unique_sources,
        'not_found': False,
        'session_id': s_id
    }


def run_rag_workspace_pipeline_stream(user, material_ids, prompt="", mode="ask", explain_level="detailed", strict_mode=True, allow_external=False, session_id=None):
    """
    Streaming variant of run_rag_workspace_pipeline emitting SSE text frames.
    Strict True RAG pipeline execution.
    """
    def _frame(payload):
        return payload

    session = get_or_create_rag_session(user, session_id, prompt, mode, strict_mode)
    s_id = session.id if session else None

    materials = StudyMaterial.objects.filter(id__in=material_ids, is_published=True)
    if not materials.exists():
        yield _frame({'type': 'error', 'message': 'No study materials selected.', 'not_found': True, 'session_id': s_id})
        yield _frame({'type': 'done', 'status': 'error', 'answer': 'Not found in the knowledge base.', 'sources': [], 'session_id': s_id})
        return

    raw_chunks = retrieve_source_chunks(material_ids, prompt, top_k=10)
    chunks = rerank_and_deduplicate_chunks(raw_chunks, min_score=0.15, max_chunks=6)

    if not chunks:
        msg = "Not found in the knowledge base."
        s_id = log_rag_query(user, mode, prompt, msg, 0, [], strict_mode, True, s_id, material_ids)
        yield _frame({'type': 'meta', 'status': 'success', 'not_found': True, 'mode': mode, 'session_id': s_id})
        yield _frame({'type': 'done', 'status': 'success', 'not_found': True, 'answer': msg, 'sources': [], 'mode': mode, 'session_id': s_id})
        return

    context_blocks = []
    unique_sources = []
    seen = set()
    for idx, c in enumerate(chunks, 1):
        context_blocks.append(f"--- SOURCE [{idx}]: {c['material_title']} (Page {c['page_number']}) ---\n{c['text']}")
        s_key = (c['material_id'], c['page_number'])
        if s_key not in seen:
            seen.add(s_key)
            unique_sources.append({
                'material_id': c['material_id'],
                'title': c['material_title'],
                'unit_title': c['unit_title'],
                'page_number': c['page_number'],
                'file_url': c['file_url'],
                'snippet': c['text'][:140] + '...' if len(c['text']) > 140 else c['text']
            })
    context_str = "\n\n".join(context_blocks)

    # Multi-turn conversation context from existing session
    history_str = ""
    if session:
        prev_msgs = list(session.messages.order_by('-created_at')[:6])
        prev_msgs.reverse()
        if prev_msgs:
            h_lines = [f"{'Student' if m.role == 'user' else 'Assistant'}: {m.content}" for m in prev_msgs]
            history_str = "\n".join(h_lines)

    system_p = (
        "You are a strict Retrieval-Augmented Generation (RAG) system.\n"
        "Your ONLY task is to answer the user request based STRICTLY and ONLY on the provided RETRIEVED CONTEXT snippets below.\n\n"
        "STRICT CONSTRAINTS:\n"
        "1. Answer ONLY using the facts present in the provided context. Do NOT use any external knowledge, assumptions, or prior training data.\n"
        "2. If the context does not contain sufficient facts to answer the user prompt completely, reply with EXACTLY: Not found in the knowledge base.\n"
        "3. For every statement or claim in your response, provide an inline citation in the format [Document Title, Page X].\n"
        "4. Keep your answer precise, grounded, deterministic, and traceable to the retrieved source chunks."
    )

    if history_str:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nRECENT CHAT HISTORY:\n{history_str}\n\nSTUDENT PROMPT: {prompt or 'Summarize key points from these chunks.'}"
    else:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nUSER PROMPT: {prompt or 'Summarize key points from these chunks.'}"

    yield _frame({'type': 'meta', 'status': 'success', 'not_found': False, 'mode': mode, 'session_id': s_id, 'sources_count': len(unique_sources)})

    collected = []
    token_count = 0

    for delta in call_phi_llm_stream(user_p, system_prompt=system_p):
        collected.append(delta)
        token_count += 1
        yield _frame({'type': 'token', 'delta': delta})

    answer = "".join(collected).strip()
    if not answer or "not found in the knowledge base" in answer.lower():
        answer = "Not found in the knowledge base."
        for i in range(0, len(answer), 6):
            yield _frame({'type': 'token', 'delta': answer[i:i+6]})

    s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, s_id, material_ids)
    yield _frame({
        'type': 'done',
        'status': 'success',
        'mode': mode,
        'answer': answer,
        'sources': unique_sources,
        'not_found': False,
        'fallback_used': False,
        'tokens': token_count,
        'session_id': s_id
    })


def generate_fallback_ask(prompt, chunks, materials):
    if chunks:
        c = chunks[0]
        return f"According to **{c['material_title']}** (Page {c['page_number']}):\n\n{c['text']}"
    m = materials.first()
    return f"Based on **{m.title}**, here is key information regarding your query: {m.summary_ai or m.description or 'Refer to document.'}"


def generate_fallback_explain(prompt, level, chunks, materials):
    hdr = f"💡 **{level.capitalize()} Topic Explanation:**\n\n"
    if chunks:
        return hdr + f"{chunks[0]['text']}\n\n*(Reference: {chunks[0]['material_title']}, Page {chunks[0]['page_number']})*"
    return hdr + "Selected materials contain foundational guidance for this topic."


def generate_fallback_summary(chunks, materials):
    res = "## 📖 Study Material Summary\n\n"
    res += "### 💡 Key Concepts\n"
    for m in materials:
        res += f"- **{m.title}**: {m.summary_ai or m.description or 'Course study resource.'}\n"
    res += "\n### 📌 Important Passages\n"
    for c in chunks[:3]:
        res += f"- **{c['material_title']}** (Page {c['page_number']}): {c['text'][:150]}...\n"
    return res


def generate_quiz_engine_data(chunks, materials):
    items = []
    sample_texts = [c['text'] for c in chunks[:5]] if chunks else [m.title for m in materials]

    for idx, txt in enumerate(sample_texts[:5], 1):
        c = chunks[idx-1] if idx-1 < len(chunks) else {'material_title': materials.first().title, 'page_number': 1}
        stmt = txt.strip().split('.')[0] if '.' in txt else txt[:70]

        items.append({
            'id': idx,
            'type': 'mcq',
            'question': f"According to {c['material_title']} (Page {c['page_number']}), which statement is correct regarding: '{stmt[:60]}...'?",
            'options': [
                f"It is a core concept documented in {c['material_title']} on Page {c['page_number']}.",
                "It applies strictly to unselected external domains.",
                "It is deprecated and not included in course materials.",
                "None of the above."
            ],
            'correct_index': 0,
            'explanation': f"This principle is explicitly covered on Page {c['page_number']} of {c['material_title']}.",
            'source': f"📚 {c['material_title']} — Page {c['page_number']}"
        })
    return items


def generate_revision_engine_data(chunks, materials):
    cards = []
    for idx, m in enumerate(materials, 1):
        cards.append({
            'id': idx,
            'front': f"What are the key topics in {m.title}?",
            'back': m.summary_ai or m.description or f"Resource uploaded for {m.classroom.title}.",
            'source': f"📚 {m.title}"
        })

    for idx, c in enumerate(chunks[:4], len(cards) + 1):
        cards.append({
            'id': idx,
            'front': f"Key Definition from {c['material_title']} (Page {c['page_number']})",
            'back': c['text'],
            'source': f"📚 {c['material_title']} — Page {c['page_number']}"
        })

    return {'flashcards': cards}


def log_rag_query(user, mode, prompt, response, retrieved_count, sources, strict_mode, not_found, session_id=None, material_ids=None):
    """
    Logs RAG query execution to audit table AND persists conversation message turns
    in RagChatMessage table for ChatGPT-style session persistence per user.
    """
    session = get_or_create_rag_session(user, session_id, prompt, mode, strict_mode)
    try:
        if session:
            if material_ids and isinstance(material_ids, (list, set, tuple)):
                try:
                    session.selected_materials.set(list(material_ids))
                except Exception:
                    pass

            # Store User Prompt Message
            if prompt:
                RagChatMessage.objects.create(
                    session=session,
                    role='user',
                    content=prompt
                )

            # Store AI Assistant Response Message
            if response:
                RagChatMessage.objects.create(
                    session=session,
                    role='assistant',
                    content=response,
                    sources=sources or []
                )

        RagQueryLog.objects.create(
            session=session,
            user=user,
            mode=mode,
            prompt=prompt or '',
            response=response or '',
            retrieved_chunks_count=retrieved_count,
            sources_cited=sources or [],
            strict_mode_applied=strict_mode,
            not_found=not_found
        )
    except Exception as e:
        print(f"[RAG Log Warning] {e}")

    return session.id if session else None
