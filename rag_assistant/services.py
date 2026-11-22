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
import hashlib
import requests
from django.utils import timezone
from django.core.cache import cache
from meetings.models import StudyMaterial, MaterialChunk
from .models import RagSession, RagChatMessage, RagQueryLog
import os
import logging
from typing import List, Dict, Any
from django.conf import settings

logger = logging.getLogger('rag')

# LLM & Embedding Endpoints Configuration (Loaded dynamically from .env via Django settings)
def get_ai_config():
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')
    gemini_model = getattr(settings, 'GEMINI_MODEL', '') or os.environ.get('GEMINI_MODEL', '')

    # Hot-reload fallback: if server was started before .env was edited, read .env directly
    if not api_key or not gemini_model:
        try:
            env_path = os.path.join(getattr(settings, 'BASE_DIR', ''), '.env')
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('GEMINI_API_KEY=') and not api_key:
                            api_key = line.split('=', 1)[1].strip()
                        elif line.startswith('GEMINI_MODEL=') and not gemini_model:
                            gemini_model = line.split('=', 1)[1].strip()
        except Exception:
            pass

    return {
        'llm_url': getattr(settings, 'AI_LLM_URL', '') or os.environ.get('AI_LLM_URL', ''),
        'bearer_token': getattr(settings, 'AI_LLM_BEARER_TOKEN', '') or os.environ.get('AI_LLM_BEARER_TOKEN', ''),
        'model_name': getattr(settings, 'AI_MODEL_NAME', '') or os.environ.get('AI_MODEL_NAME', ''),
        'embedding_url': getattr(settings, 'AI_EMBEDDING_URL', '') or os.environ.get('AI_EMBEDDING_URL', ''),
        'embedding_model': getattr(settings, 'AI_EMBEDDING_MODEL', '') or os.environ.get('AI_EMBEDDING_MODEL', ''),
        'gemini_api_key': api_key,
        'gemini_model': gemini_model,
    }


import time

_EMBEDDING_OFFLINE_UNTIL = 0.0


def get_gemini_embedding(text):
    """
    Generates dense vector embedding using Google Gemini embedding API.
    Supports gemini-embedding-001 with fallback to text-embedding-004.
    """
    cfg = get_ai_config()
    api_key = cfg.get('gemini_api_key')
    if not api_key or not text or not text.strip():
        return None

    for model_name in ('gemini-embedding-001', 'text-embedding-004'):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={api_key}"
        payload = {
            "model": f"models/{model_name}",
            "content": {
                "parts": [{"text": text[:2000]}]
            }
        }
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                values = data.get('embedding', {}).get('values')
                if values:
                    return values
        except Exception as err:
            logger.warning(f"[Gemini Embedding Warning ({model_name})] {err}")
    return None


def get_nomic_embedding(text):
    """
    Generates dense float vector embedding using:
    1. Google Gemini text-embedding-004 (if GEMINI_API_KEY configured)
    2. Ollama nomic-embed-text server
    Uses a 30s circuit breaker if service is offline to prevent batch indexing timeouts.
    """
    global _EMBEDDING_OFFLINE_UNTIL
    if not text or not text.strip():
        return None

    cfg = get_ai_config()

    # 1. Try Gemini Free API Embeddings if key configured
    if cfg.get('gemini_api_key'):
        emb = get_gemini_embedding(text)
        if emb:
            return emb

    now = time.time()
    if now < _EMBEDDING_OFFLINE_UNTIL:
        return None

    # 2. Try Ollama local / remote embeddings
    if cfg['embedding_url']:
        url = f"{cfg['embedding_url'].rstrip('/')}/api/embeddings"
        payload = {
            "model": cfg['embedding_model'],
            "prompt": text[:2000]
        }
        emb_headers = {'Content-Type': 'application/json'}
        if cfg['bearer_token']:
            emb_headers['Authorization'] = f"Bearer {cfg['bearer_token']}"
        try:
            res = requests.post(url, json=payload, headers=emb_headers, timeout=25.0)
            if res.status_code == 200:
                data = res.json()
                if data.get('embedding'):
                    return data.get('embedding')
        except Exception:
            pass

    _EMBEDDING_OFFLINE_UNTIL = now + 10.0
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


# ==============================================================================
# RAG PRODUCTION CONFIGURATION CONSTANTS
# ==============================================================================
RAG_TOP_K_INITIAL = 20               # Candidate chunks pool
RAG_MIN_SIMILARITY_THRESHOLD = 0.08  # Initial generous similarity floor
RAG_MIN_RERANK_THRESHOLD = 0.12      # Minimum score threshold after reranking
RAG_MAX_FINAL_CHUNKS = 4            # Maximum final chunks sent to LLM prompt (optimized for fast local inference)
RAG_FALLBACK_SEARCH_ENABLED = True     # Enable multi-stage fallback retrieval
RAG_DEBUG_LOGGING = True            # Enable server-side developer telemetry logging


def log_rag_debug(event_name, data):
    """Outputs structured developer debug telemetry logging to server console."""
    if RAG_DEBUG_LOGGING:
        try:
            print(f"[RAG TELEMETRY | {event_name}] {json.dumps(data, default=str)}")
        except Exception:
            print(f"[RAG TELEMETRY | {event_name}] {data}")


TASK_OR_META_KEYWORDS = {
    'mcq', 'mcqs', 'quiz', 'quizzes', 'question', 'questions', 'test', 'exam',
    'flashcard', 'flashcards', 'summary', 'summarize', 'overview', 'outline',
    'notes', 'key points', 'main topics', 'bullet points', 'generate', 'create',
    'make', 'give', 'prepare', 'list', 'revision', 'practice', 'explain', 'detail'
}


def is_task_or_meta_prompt(prompt):
    """
    Returns True if user prompt is a study task/meta instruction (e.g. 'generate mcqs', 'summarize', 'create quiz')
    rather than a specific topical keyword search.
    """
    if not prompt or not prompt.strip():
        return True
    cleaned = prompt.lower().strip()
    words = set(re.findall(r'\b\w+\b', cleaned))
    if words.intersection(TASK_OR_META_KEYWORDS):
        return True
    if len(words) <= 4 and ('this' in words or 'it' in words or 'document' in words or 'material' in words or 'paper' in words):
        return True
    return False


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


def rerank_and_deduplicate_chunks(chunks, min_score=RAG_MIN_RERANK_THRESHOLD, max_chunks=RAG_MAX_FINAL_CHUNKS):
    """
    Reranks retrieved chunks by relevance score, filters out chunks below min_score threshold,
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
                if overlap > 0.80:
                    is_dup = True
                    break
        if not is_dup:
            seen_texts.append(text_snippet)
            filtered.append(c)
            if len(filtered) >= max_chunks:
                break

    return filtered


# ==============================================================================
# ADJUSTMENT 2: SEMANTIC REDIS CACHE
# ==============================================================================

def get_rag_cached_response(material_ids, prompt, mode="ask", query_vec=None):
    """
    Checks Redis/Django cache for exact or semantic matches.
    1. Exact query match in Redis (instant <5ms).
    2. Semantic vector match (cosine sim >= 0.95 with cached queries in same materials & mode).
    """
    if not prompt or not material_ids:
        return None

    mat_key = "_".join(sorted(str(m) for m in material_ids))
    clean_p = rewrite_query(prompt).lower().strip()
    p_hash = hashlib.sha256(clean_p.encode('utf-8')).hexdigest()[:16]

    # 1. Exact match
    exact_cache_key = f"edumi:rag:cache:{mat_key}:{mode}:{p_hash}"
    try:
        cached_data = cache.get(exact_cache_key)
        if cached_data:
            log_rag_debug("REDIS_EXACT_CACHE_HIT", {"key": exact_cache_key, "prompt": prompt})
            return cached_data
    except Exception:
        pass

    # 2. Semantic matching if query_vec is available
    if query_vec:
        try:
            index_key = f"edumi:rag:qindex:{mat_key}:{mode}"
            recent_queries = cache.get(index_key) or []
            for q_entry in recent_queries:
                q_vec = q_entry.get('vec')
                if q_vec and cosine_similarity(query_vec, q_vec) >= 0.95:
                    ref_key = q_entry.get('key')
                    hit = cache.get(ref_key)
                    if hit:
                        log_rag_debug("REDIS_SEMANTIC_CACHE_HIT", {
                            "similarity": round(cosine_similarity(query_vec, q_vec), 3),
                            "matched_query": q_entry.get('text')
                        })
                        return hit
        except Exception:
            pass

    return None


def set_rag_cached_response(material_ids, prompt, mode, payload, query_vec=None, ttl=3600):
    """
    Saves RAG response in Redis cache and indexes query vector for semantic cache hits.
    """
    if not prompt or not material_ids or not payload or not payload.get('answer'):
        return
    mat_key = "_".join(sorted(str(m) for m in material_ids))
    clean_p = rewrite_query(prompt).lower().strip()
    p_hash = hashlib.sha256(clean_p.encode('utf-8')).hexdigest()[:16]
    cache_key = f"edumi:rag:cache:{mat_key}:{mode}:{p_hash}"

    try:
        cache.set(cache_key, payload, timeout=ttl)

        if query_vec:
            index_key = f"edumi:rag:qindex:{mat_key}:{mode}"
            recent_queries = cache.get(index_key) or []
            recent_queries.insert(0, {
                'text': clean_p,
                'vec': query_vec,
                'key': cache_key
            })
            cache.set(index_key, recent_queries[:30], timeout=ttl)
    except Exception:
        pass


# ==============================================================================
# ADJUSTMENT 5: RECIPROCAL RANK FUSION (RRF) & PARENT-DOCUMENT RETRIEVAL
# ==============================================================================

def retrieve_source_chunks(material_ids, query, top_k=RAG_TOP_K_INITIAL):
    """
    Retrieves and ranks relevant text chunks using Reciprocal Rank Fusion (RRF):
    Merges dense vector search ranking with BM25 lexical ranking:
      RRF_score(d) = 0.70 / (60 + rank_vec) + 0.30 / (60 + rank_lex)
    Preserves parent_context in each candidate for Parent-Document Retrieval (Adjustment 4).
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

    # Check if prompt is a document-level task (e.g. generate MCQs, summarize)
    is_meta = is_task_or_meta_prompt(query)

    # Get query embedding for semantic search
    query_vec = get_nomic_embedding(effective_query) if effective_query else None

    query_clean = re.sub(r'[^\w\s]', '', (effective_query or '').lower())
    query_tokens = [w for w in query_clean.split() if len(w) > 2]

    vec_candidates = []
    lex_candidates = []

    for chunk in chunks:
        c_text = chunk.chunk_text.lower()
        m_title = chunk.material.title.lower()

        # 1. Lexical Keyword & N-gram Matching Score
        kw_score = 0.0
        matches = 0
        for token in query_tokens:
            cnt = c_text.count(token)
            if cnt > 0:
                kw_score += (1.0 + math.log(cnt))
                matches += 1
            if token in m_title:
                kw_score += 3.0

        if len(query_tokens) == 1 and query_tokens[0] in c_text:
            kw_score += 4.0

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

        vec_candidates.append((chunk, sem_sim))
        lex_candidates.append((chunk, kw_norm))

    # Sort each stream independently for Reciprocal Rank Fusion
    vec_candidates.sort(key=lambda x: x[1], reverse=True)
    lex_candidates.sort(key=lambda x: x[1], reverse=True)

    vec_ranks = {item[0].id: rank for rank, item in enumerate(vec_candidates, 1)}
    lex_ranks = {item[0].id: rank for rank, item in enumerate(lex_candidates, 1)}

    k_rrf = 60
    scored = []
    for chunk, sem_sim in vec_candidates:
        r_vec = vec_ranks.get(chunk.id, 999)
        r_lex = lex_ranks.get(chunk.id, 999)

        # Reciprocal Rank Fusion formula scaled to [0, 1] range
        raw_rrf = (0.70 / (k_rrf + r_vec)) + (0.30 / (k_rrf + r_lex))
        rrf_score = raw_rrf * k_rrf

        # For task/meta prompts (e.g. generate MCQs, summarize), assign structural baseline
        if is_meta:
            baseline = max(0.35, 0.60 / (chunk.chunk_index + 1))
            rrf_score = max(rrf_score, baseline)

        page_num = chunk.page_number or (chunk.chunk_index + 1)
        unit_title = chunk.material.unit.title if chunk.material.unit else "General"
        parent_ctx = (chunk.metadata or {}).get('parent_context') or chunk.chunk_text

        scored.append({
            'chunk_id': chunk.id,
            'material_id': chunk.material.id,
            'material_title': chunk.material.title,
            'unit_title': unit_title,
            'page_number': page_num,
            'chunk_index': chunk.chunk_index,
            'text': chunk.chunk_text,
            'parent_context': parent_ctx,
            'score': rrf_score,
            'file_url': chunk.material.file.url if chunk.material.file else None,
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_k]


def call_gemini_llm_stream(prompt, system_prompt=""):
    """
    Calls Google Gemini Free REST API with Server-Sent Events (SSE) streaming.
    Yields individual tokens/text chunks as they arrive from Gemini 1.5 Flash.
    """
    cfg = get_ai_config()
    api_key = cfg.get('gemini_api_key')
    if not api_key:
        return

    model = cfg.get('gemini_model')
    if not model or not api_key:
        return
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048
        }
    }
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    try:
        res = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            stream=True,
            timeout=(10, 120)
        )
        if res.status_code == 200:
            for line in res.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8')
                if line_str.startswith('data:'):
                    line_str = line_str[5:].strip()
                if not line_str or line_str == '[DONE]':
                    continue
                try:
                    data = json.loads(line_str)
                    candidates = data.get('candidates', [])
                    if candidates:
                        parts = candidates[0].get('content', {}).get('parts', [])
                        for part in parts:
                            text = part.get('text', '')
                            if text:
                                yield text
                except Exception:
                    continue
            return
        else:
            logger.warning(f"[Gemini API Stream HTTP Error] status={res.status_code}: {res.text[:200]}")
    except Exception as err:
        logger.warning(f"[Gemini API Stream Exception] {err}")


def call_llm_stream_with_engine(prompt, system_prompt="", provider='auto'):
    """
    Generator that yields tuples of (token, engine_name).
    Supported providers:
      - 'auto': tries Google Gemini first, falls back to Ollama local/remote.
      - 'gemini': directly calls Google Gemini (fails over to grounded doc synthesis if offline).
      - 'local': directly calls local/remote Ollama (bypasses Google Gemini).
    """
    cfg = get_ai_config()
    p = (provider or 'auto').lower()

    # 1. Try Google Gemini API if provider is 'auto' or 'gemini'
    if p in ('auto', 'gemini') and cfg.get('gemini_api_key'):
        gemini_emitted = False
        for token in call_gemini_llm_stream(prompt, system_prompt=system_prompt):
            gemini_emitted = True
            yield token, 'gemini'
        if gemini_emitted:
            return

    # If user explicitly locked to 'gemini' and it failed or was not configured, do not fall back to local
    if p == 'gemini':
        return

    # 2. Try Local / Custom Ollama Endpoint
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
            if 'response' in data:
                return data['response'], data.get('done', False)
        except Exception:
            pass
        return None, False

    # 2a. Primary LLM Endpoint (Cloudflare / Custom endpoint)
    if cfg['llm_url']:
        try:
            response = requests.post(
                cfg['llm_url'],
                headers=headers,
                json=payload,
                stream=True,
                timeout=(30, 240)
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
                            yield part, 'local'
                        if done:
                            break
                    except Exception:
                        continue
                if emitted_any:
                    return
        except Exception as err:
            print(f"[RAG Workspace LLM Stream Error] {err}")

    # 2b. Local / remote Ollama generate API
    if cfg['embedding_url']:
        try:
            ollama_generate_url = f"{cfg['embedding_url'].rstrip('/')}/api/generate"
            ollama_payload = {
                "model": cfg['model_name'],
                "prompt": full_prompt,
                "stream": True
            }
            res = requests.post(ollama_generate_url, headers=headers, json=ollama_payload, stream=True, timeout=(30, 240))
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
                            yield response_part, 'local'
                        if data.get('done', False):
                            break
                    except Exception:
                        continue
                if emitted_any:
                    return
        except Exception as err:
            print(f"[Ollama Fallback LLM Stream Error] {err}")


def call_phi_llm_stream(prompt, system_prompt="", provider='auto'):
    """
    Generator that yields individual text tokens as they arrive from streaming API.
    Delegates to call_llm_stream_with_engine.
    """
    for token, _ in call_llm_stream_with_engine(prompt, system_prompt=system_prompt, provider=provider):
        yield token


def call_phi_llm_with_engine(prompt, system_prompt="", provider='auto'):
    """Calls configured LLM with streaming payload aggregation and returns (answer, engine_name)."""
    tokens = []
    engine = 'grounded_fallback'
    for delta, eng in call_llm_stream_with_engine(prompt, system_prompt=system_prompt, provider=provider):
        tokens.append(delta)
        engine = eng
    return "".join(tokens) or None, engine


def call_phi_llm(prompt, system_prompt="", provider='auto'):
    """Calls primary configured LLM with streaming payload aggregation."""
    text, _ = call_phi_llm_with_engine(prompt, system_prompt=system_prompt, provider=provider)
    return text


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


def get_fallback_document_chunks(material_ids, max_chunks=RAG_MAX_FINAL_CHUNKS):
    """Retrieves top structural text chunks directly from selected published study materials."""
    if not material_ids:
        return []
    fallback_db_chunks = MaterialChunk.objects.filter(
        material_id__in=material_ids,
        material__is_published=True
    ).select_related('material', 'material__unit').order_by('chunk_index')[:max_chunks]
    
    chunks = []
    for idx, chunk in enumerate(fallback_db_chunks):
        page_num = chunk.page_number or (chunk.chunk_index + 1)
        unit_title = chunk.material.unit.title if chunk.material.unit else "General"
        chunks.append({
            'chunk_id': chunk.id,
            'material_id': chunk.material.id,
            'material_title': chunk.material.title,
            'unit_title': unit_title,
            'page_number': page_num,
            'chunk_index': chunk.chunk_index,
            'text': chunk.chunk_text,
            'score': 0.50,
            'file_url': chunk.material.file.url if chunk.material.file else None,
        })
    return chunks


def execute_multi_stage_retrieval(material_ids, prompt):
    """
    Multi-stage retrieval execution with Developer Telemetry Logging:
    Stage 1: Primary Hybrid Search (Dense Vector + BM25 Lexical).
    Stage 2: Fallback Retrieval (N-gram/Token expansion & Structural Fallback).
    """
    rewritten = rewrite_query(prompt)
    log_rag_debug("RETRIEVAL_START", {
        "selected_material_ids": material_ids,
        "raw_query": prompt,
        "rewritten_query": rewritten,
        "is_meta_prompt": is_task_or_meta_prompt(prompt)
    })

    # Stage 1: Primary Hybrid Search
    raw_chunks = retrieve_source_chunks(material_ids, prompt, top_k=RAG_TOP_K_INITIAL)
    chunks = rerank_and_deduplicate_chunks(raw_chunks, min_score=RAG_MIN_RERANK_THRESHOLD, max_chunks=RAG_MAX_FINAL_CHUNKS)

    log_rag_debug("STAGE1_RESULT", {
        "raw_candidates_count": len(raw_chunks),
        "reranked_count": len(chunks),
        "top_scores": [round(c['score'], 3) for c in chunks[:5]]
    })

    # Stage 2: Fallback Retrieval Strategy
    if RAG_FALLBACK_SEARCH_ENABLED and len(chunks) < 2:
        fallback_reason = "Low candidate score or task prompt"
        log_rag_debug("FALLBACK_TRIGGERED", {"reason": fallback_reason, "current_chunks": len(chunks)})
        
        # Pass A: Token expansion / Raw query fallback
        if prompt and prompt != rewritten:
            raw_pass_chunks = retrieve_source_chunks(material_ids, prompt, top_k=RAG_TOP_K_INITIAL)
            raw_reranked = rerank_and_deduplicate_chunks(raw_pass_chunks, min_score=0.10, max_chunks=RAG_MAX_FINAL_CHUNKS)
            if raw_reranked:
                chunks.extend([c for c in raw_reranked if c['chunk_id'] not in [x['chunk_id'] for x in chunks]])
                chunks = sorted(chunks, key=lambda x: x['score'], reverse=True)[:RAG_MAX_FINAL_CHUNKS]

        # Pass B: Structural fallback for task instructions (MCQs, Quiz, Summary, Flashcards)
        if not chunks and is_task_or_meta_prompt(prompt):
            chunks = get_fallback_document_chunks(material_ids, max_chunks=RAG_MAX_FINAL_CHUNKS)
            log_rag_debug("STRUCTURAL_FALLBACK_APPLIED", {"retrieved_fallback_count": len(chunks)})

    log_rag_debug("FINAL_RETRIEVAL_CHUNKS", {
        "final_chunks_sent": len(chunks),
        "chunk_sources": [{'title': c['material_title'], 'page': c['page_number'], 'score': round(c['score'], 3)} for c in chunks]
    })

    return chunks


def _filter_authorized_materials(user, material_ids):
    """Enforce strict classroom authorization boundary for RAG materials."""
    if not user or not user.is_authenticated:
        return []
    if getattr(user, 'is_superuser', False):
        return list(StudyMaterial.objects.filter(id__in=material_ids, is_published=True).values_list('id', flat=True))
    if hasattr(user, 'userprofile') and user.userprofile.user_type in ('teacher', 'admin'):
        return list(StudyMaterial.objects.filter(
            id__in=material_ids,
            is_published=True,
            classroom__teacher=user
        ).values_list('id', flat=True))
    return list(StudyMaterial.objects.filter(
        id__in=material_ids,
        is_published=True,
        classroom__memberships__student=user,
        classroom__memberships__status='approved'
    ).values_list('id', flat=True))


def run_rag_workspace_pipeline(user, material_ids, prompt="", mode="ask", explain_level="detailed", strict_mode=True, allow_external=False, session_id=None, provider="auto"):
    """
    Main synchronous entrypoint for processing user study requests in RAG AI Study Workspace.
    Production-Grade RAG Pipeline with Semantic Redis Caching, Parent-Document Retrieval,
    and Evidence Validation.
    """
    session = get_or_create_rag_session(user, session_id, prompt, mode, strict_mode)
    s_id = session.id if session else None

    # Defense-in-depth: Enforce authorized classroom membership
    material_ids = _filter_authorized_materials(user, material_ids)
    if not material_ids:
        return {
            'status': 'error',
            'message': 'No authorized study materials selected.',
            'not_found': True,
            'answer': 'Access denied or no valid study resources selected.',
            'sources': [],
            'session_id': s_id,
            'engine_used': 'none'
        }

    # Adjustment 2: Semantic Redis Cache Check (<10ms instant response)
    cached = get_rag_cached_response(material_ids, prompt, mode)
    if cached:
        s_id = log_rag_query(user, mode, prompt, cached['answer'], len(cached.get('sources', [])), cached.get('sources', []), strict_mode, False, s_id, material_ids)
        return {
            'status': 'success',
            'mode': mode,
            'answer': cached['answer'],
            'sources': cached.get('sources', []),
            'not_found': False,
            'from_cache': True,
            'session_id': s_id,
            'engine_used': 'cache'
        }

    chunks = execute_multi_stage_retrieval(material_ids, prompt)

    if not chunks:
        msg = "Not found in the selected documents."
        s_id = log_rag_query(user, mode, prompt, msg, 0, [], strict_mode, True, s_id, material_ids)
        return {
            'status': 'success',
            'not_found': True,
            'answer': msg,
            'sources': [],
            'can_fallback_external': False,
            'mode': mode,
            'session_id': s_id,
            'engine_used': 'grounded_fallback'
        }

    # Adjustment 4: Parent-Document Retrieval (Provide full parent context to LLM, concise snippet to UI)
    context_blocks = []
    unique_sources = []
    seen = set()
    seen_parents = set()

    for idx, c in enumerate(chunks, 1):
        parent_text = c.get('parent_context') or c['text']
        p_hash = hashlib.md5(parent_text.strip().encode('utf-8')).hexdigest()
        if p_hash not in seen_parents:
            seen_parents.add(p_hash)
            context_blocks.append(f"--- SOURCE [{idx}]: {c['material_title']} (Page {c['page_number']}) ---\n{parent_text}")
        else:
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
        "You are an expert AI Study Assistant for educational courses.\n"
        "Your task is to answer the student's question accurately using the RETRIEVED CONTEXT below.\n\n"
        "GUIDELINES:\n"
        "1. STRICT GROUNDING: Base your explanation on the facts, definitions, and details in the RETRIEVED CONTEXT.\n"
        "2. INLINE CITATIONS: For every key fact, cite the source as [Document Title, Page X].\n"
        "3. PARTIAL COVERAGE: If the context answers part of the prompt, explain what is available from the text and note what specific details were missing.\n"
        "4. HELPFUL & DIRECT: Give a clear, direct, and structured response based on the document passages."
    )
    
    if history_str:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nRECENT CHAT HISTORY:\n{history_str}\n\nSTUDENT QUESTION: {prompt or 'Summarize key points from these chunks.'}"
    else:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nSTUDENT QUESTION: {prompt or 'Summarize key points from these chunks.'}"

    answer, engine_used = call_phi_llm_with_engine(user_p, system_p, provider=provider)
    if not answer or answer.strip() == "" or answer.strip().lower() in ("not found in the selected documents.", "not found in the selected documents"):
        if chunks:
            answer = generate_fallback_ask(prompt, chunks)
            engine_used = 'grounded_fallback'
        else:
            answer = "Not found in the selected documents."
            engine_used = 'grounded_fallback'

    s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, s_id, material_ids)

    # Save to Semantic Redis Cache
    set_rag_cached_response(material_ids, prompt, mode, {'answer': answer, 'sources': unique_sources})

    return {
        'status': 'success',
        'mode': mode,
        'answer': answer,
        'sources': unique_sources,
        'not_found': False,
        'session_id': s_id,
        'engine_used': engine_used
    }


def run_rag_workspace_pipeline_stream(user, material_ids, prompt="", mode="ask", explain_level="detailed", strict_mode=True, allow_external=False, session_id=None, provider="auto"):
    """
    Streaming variant of run_rag_workspace_pipeline emitting SSE text frames.
    Production-Grade RAG Pipeline execution with Semantic Redis Cache and Parent-Document Retrieval.
    """
    def _frame(payload):
        return payload

    session = get_or_create_rag_session(user, session_id, prompt, mode, strict_mode)
    s_id = session.id if session else None

    # Defense-in-depth: Enforce authorized classroom membership
    material_ids = _filter_authorized_materials(user, material_ids)
    if not material_ids:
        yield _frame({'type': 'error', 'message': 'No authorized study materials selected.', 'not_found': True, 'session_id': s_id})
        yield _frame({'type': 'done', 'status': 'error', 'answer': 'Access denied or no valid study resources selected.', 'sources': [], 'session_id': s_id, 'engine_used': 'none'})
        return

    # Adjustment 2: Instant Cache Hit for Streaming
    cached = get_rag_cached_response(material_ids, prompt, mode)
    if cached:
        yield _frame({'type': 'meta', 'status': 'success', 'not_found': False, 'mode': mode, 'session_id': s_id, 'sources_count': len(cached.get('sources', []))})
        yield _frame({'type': 'status', 'message': 'Loaded from instant semantic cache...'})
        cached_answer = cached['answer']
        chunk_stride = 24
        for i in range(0, len(cached_answer), chunk_stride):
            yield _frame({'type': 'token', 'delta': cached_answer[i:i+chunk_stride]})
        s_id = log_rag_query(user, mode, prompt, cached_answer, len(cached.get('sources', [])), cached.get('sources', []), strict_mode, False, s_id, material_ids)
        yield _frame({
            'type': 'done',
            'status': 'success',
            'mode': mode,
            'answer': cached_answer,
            'sources': cached.get('sources', []),
            'not_found': False,
            'from_cache': True,
            'session_id': s_id,
            'engine_used': 'cache'
        })
        return

    chunks = execute_multi_stage_retrieval(material_ids, prompt)

    if not chunks:
        msg = "Not found in the selected documents."
        s_id = log_rag_query(user, mode, prompt, msg, 0, [], strict_mode, True, s_id, material_ids)
        yield _frame({'type': 'meta', 'status': 'success', 'not_found': True, 'mode': mode, 'session_id': s_id})
        yield _frame({'type': 'done', 'status': 'success', 'not_found': True, 'answer': msg, 'sources': [], 'mode': mode, 'session_id': s_id, 'engine_used': 'grounded_fallback'})
        return

    # Adjustment 4: Parent-Document Retrieval context assembly in stream
    context_blocks = []
    unique_sources = []
    seen = set()
    seen_parents = set()
    for idx, c in enumerate(chunks, 1):
        parent_text = c.get('parent_context') or c['text']
        p_hash = hashlib.md5(parent_text.strip().encode('utf-8')).hexdigest()
        if p_hash not in seen_parents:
            seen_parents.add(p_hash)
            context_blocks.append(f"--- SOURCE [{idx}]: {c['material_title']} (Page {c['page_number']}) ---\n{parent_text}")
        else:
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
        "You are an expert AI Study Assistant for educational courses.\n"
        "Your task is to answer the student's question accurately using the RETRIEVED CONTEXT below.\n\n"
        "GUIDELINES:\n"
        "1. STRICT GROUNDING: Base your explanation on the facts, definitions, and details in the RETRIEVED CONTEXT.\n"
        "2. INLINE CITATIONS: For every key fact, cite the source as [Document Title, Page X].\n"
        "3. PARTIAL COVERAGE: If the context answers part of the prompt, explain what is available from the text and note what specific details were missing.\n"
        "4. HELPFUL & DIRECT: Give a clear, direct, and structured response based on the document passages."
    )

    if history_str:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nRECENT CHAT HISTORY:\n{history_str}\n\nSTUDENT QUESTION: {prompt or 'Summarize key points from these chunks.'}"
    else:
        user_p = f"RETRIEVED CONTEXT:\n{context_str}\n\nSTUDENT QUESTION: {prompt or 'Summarize key points from these chunks.'}"

    yield _frame({'type': 'meta', 'status': 'success', 'not_found': False, 'mode': mode, 'session_id': s_id, 'sources_count': len(unique_sources)})
    yield _frame({'type': 'status', 'message': f'Found {len(chunks)} relevant sections. Analyzing with AI...'})

    collected = []
    token_count = 0
    engine_used = 'grounded_fallback'

    for delta, engine in call_llm_stream_with_engine(user_p, system_prompt=system_p, provider=provider):
        collected.append(delta)
        token_count += 1
        engine_used = engine
        yield _frame({'type': 'token', 'delta': delta})

    answer = "".join(collected).strip()
    if not answer or answer.strip().lower() in ("not found in the selected documents.", "not found in the selected documents"):
        if chunks:
            log_rag_debug("LLM_EMPTY_OR_GENERIC_FALLBACK", {"reason": "Using grounded document synthesis"})
            answer = generate_fallback_ask(prompt, chunks)
            engine_used = 'grounded_fallback'
            for i in range(0, len(answer), 12):
                yield _frame({'type': 'token', 'delta': answer[i:i+12]})
        else:
            answer = "Not found in the selected documents."
            engine_used = 'grounded_fallback'
            for i in range(0, len(answer), 6):
                yield _frame({'type': 'token', 'delta': answer[i:i+6]})

    s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, s_id, material_ids)

    # Save to Semantic Redis Cache
    set_rag_cached_response(material_ids, prompt, mode, {'answer': answer, 'sources': unique_sources})

    yield _frame({
        'type': 'done',
        'status': 'success',
        'mode': mode,
        'answer': answer,
        'sources': unique_sources,
        'not_found': False,
        'fallback_used': False,
        'tokens': token_count,
        'session_id': s_id,
        'engine_used': engine_used
    })


def generate_fallback_ask(prompt, chunks, materials=None):
    if chunks:
        c = chunks[0]
        return f"According to **{c['material_title']}** (Page {c['page_number']}):\n\n{c['text']}"
    if materials:
        m = materials.first() if hasattr(materials, 'first') else (materials[0] if materials else None)
        if m:
            return f"Based on **{m.title}**, here is key information regarding your query: {m.summary_ai or m.description or 'Refer to document.'}"
    return "Not found in the selected documents."


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


# ==============================================================================
# RAGQueryService - pgvector & Hybrid Search Service (Phase 3.2 Refactor)
# ==============================================================================
class RAGQueryService:
    """
    RAG Query Service with pgvector support (Phase 3.2).
    Uses PostgreSQL pgvector CosineDistance when available,
    with automatic Python numpy/math fallback when running on SQLite or without pgvector.
    """
    def __init__(self, classroom_id: int):
        self.classroom_id = classroom_id
        self.model = None
        self.use_pgvector = self._check_pgvector_available()
        if not self.use_pgvector:
            logger.info("pgvector not available, using Python similarity fallback")

    def _check_pgvector_available(self) -> bool:
        from django.db import connection
        try:
            if connection.vendor != 'postgresql':
                return False
            with connection.cursor() as cursor:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');")
                res = cursor.fetchone()
                return bool(res and res[0])
        except Exception:
            return False

    def retrieve_chunks(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Retrieve most relevant chunks for query using pgvector or python fallback."""
        if not query or not query.strip():
            return []

        query_embedding = self._generate_embedding(query)

        if self.use_pgvector and query_embedding:
            return self._retrieve_with_pgvector(query_embedding, top_k, min_similarity)
        else:
            return self._retrieve_with_python(query_embedding, top_k, min_similarity)

    def _generate_embedding(self, text: str) -> list:
        emb = get_nomic_embedding(text)
        if emb:
            return emb
        try:
            from sentence_transformers import SentenceTransformer
            if not self.model:
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
            return self.model.encode(text).tolist()
        except Exception:
            return [0.0] * 384

    def _retrieve_with_pgvector(
        self,
        query_embedding: list,
        top_k: int,
        min_similarity: float
    ) -> List[Dict[str, Any]]:
        try:
            from pgvector.django import CosineDistance
            chunks = MaterialChunk.objects.filter(
                material__classroom_id=self.classroom_id,
                material__is_published=True,
                embedding_pgvector__isnull=False
            ).annotate(
                similarity=1 - CosineDistance('embedding_pgvector', query_embedding)
            ).filter(
                similarity__gte=min_similarity
            ).select_related('material').order_by('-similarity')[:top_k]

            results = []
            for chunk in chunks:
                results.append({
                    'chunk_id': chunk.id,
                    'chunk_text': chunk.chunk_text,
                    'similarity': float(chunk.similarity),
                    'material_id': chunk.material_id,
                    'material_title': chunk.material.title,
                    'page_number': chunk.page_number,
                    'chunk_index': chunk.chunk_index,
                })
            return results
        except Exception as e:
            logger.warning(f"pgvector query error, falling back to python: {e}")
            return self._retrieve_with_python(query_embedding, top_k, min_similarity)

    def _retrieve_with_python(
        self,
        query_embedding: list,
        top_k: int,
        min_similarity: float
    ) -> List[Dict[str, Any]]:
        chunks = MaterialChunk.objects.filter(
            material__classroom_id=self.classroom_id,
            material__is_published=True
        ).select_related('material')

        if not chunks.exists() or not query_embedding:
            return []

        scored = []
        for chunk in chunks:
            vec = chunk.embedding_vector or chunk.embedding_pgvector
            if not vec:
                continue
            sim = cosine_similarity(query_embedding, vec)
            if sim >= min_similarity:
                scored.append((chunk, float(sim)))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for chunk, similarity in scored[:top_k]:
            results.append({
                'chunk_id': chunk.id,
                'chunk_text': chunk.chunk_text,
                'similarity': similarity,
                'material_id': chunk.material_id,
                'material_title': chunk.material.title,
                'page_number': chunk.page_number,
                'chunk_index': chunk.chunk_index,
            })
        return results

    def full_text_search_fallback(
        self,
        query: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        from django.db import connection
        if connection.vendor == 'postgresql':
            try:
                from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
                chunks = MaterialChunk.objects.filter(
                    material__classroom_id=self.classroom_id,
                    material__is_published=True
                ).annotate(
                    search=SearchVector('chunk_text'),
                    rank=SearchRank(SearchVector('chunk_text'), SearchQuery(query))
                ).filter(
                    rank__gte=0.1
                ).select_related('material').order_by('-rank')[:top_k]

                results = []
                for chunk in chunks:
                    results.append({
                        'chunk_id': chunk.id,
                        'chunk_text': chunk.chunk_text,
                        'relevance': float(chunk.rank),
                        'material_id': chunk.material_id,
                        'material_title': chunk.material.title,
                        'page_number': chunk.page_number,
                        'chunk_index': chunk.chunk_index,
                        'search_type': 'full_text',
                    })
                return results
            except Exception:
                pass

        tokens = [w.lower() for w in re.findall(r'\b\w+\b', query) if len(w) > 2]
        if not tokens:
            return []
        chunks = MaterialChunk.objects.filter(
            material__classroom_id=self.classroom_id,
            material__is_published=True
        ).select_related('material')
        scored = []
        for c in chunks:
            c_lower = c.chunk_text.lower()
            cnt = sum(c_lower.count(t) for t in tokens)
            if cnt > 0:
                scored.append((c, cnt))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [{
            'chunk_id': c.id,
            'chunk_text': c.chunk_text,
            'relevance': float(cnt),
            'material_id': c.material_id,
            'material_title': c.material.title,
            'page_number': c.page_number,
            'chunk_index': c.chunk_index,
            'search_type': 'lexical',
        } for c, cnt in scored[:top_k]]

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        vector_results = self.retrieve_chunks(query, top_k=top_k, min_similarity=0.1)
        text_results = self.full_text_search_fallback(query, top_k=top_k)

        seen = set()
        merged = []
        for res in vector_results + text_results:
            cid = res['chunk_id']
            if cid not in seen:
                seen.add(cid)
                merged.append(res)

        merged.sort(key=lambda x: x.get('similarity', x.get('relevance', 0)), reverse=True)
        return merged[:top_k]
