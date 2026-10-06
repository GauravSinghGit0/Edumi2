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


def retrieve_source_chunks(material_ids, query, top_k=6):
    """
    Retrieves and ranks relevant text chunks using Hybrid Search:
    Combines nomic-embed-text Cosine Vector Similarity (75% weight) with BM25 Keyword Matching (25% weight).
    """
    if not material_ids:
        return []

    chunks = MaterialChunk.objects.filter(
        material_id__in=material_ids,
        material__is_published=True
    ).select_related('material', 'material__unit')

    if not chunks.exists():
        return []

    # Get query embedding for semantic search
    query_vec = get_nomic_embedding(query) if query else None

    query_clean = re.sub(r'[^\w\s]', '', (query or '').lower())
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

        # 3. Hybrid Combined Score
        if query_vec and chunk_vec:
            final_score = (0.75 * sem_sim) + (0.25 * min(1.0, kw_norm / 5.0))
        elif query_tokens:
            final_score = kw_norm
        else:
            final_score = 1.0 / (chunk.chunk_index + 1)

        if final_score > 0.05 or not query_tokens:
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


def run_rag_workspace_pipeline(user, material_ids, prompt="", mode="ask", explain_level="detailed", strict_mode=True, allow_external=False, session_id=None):
    """
    Main synchronous entrypoint for processing user study requests in RAG AI Study Workspace.
    """
    materials = StudyMaterial.objects.filter(id__in=material_ids, is_published=True)
    if not materials.exists():
        return {
            'status': 'error',
            'message': 'No study materials selected.',
            'not_found': True,
            'answer': 'Please select at least one study resource to start an AI study session.',
            'sources': []
        }

    chunks = retrieve_source_chunks(material_ids, prompt, top_k=6)
    max_score = max([c['score'] for c in chunks]) if chunks else 0.0

    if strict_mode and (not chunks or (prompt and max_score < 0.12 and mode in ['ask', 'explain'])):
        s_id = log_rag_query(user, mode, prompt, "I couldn't find this information in your selected study materials.", 0, [], strict_mode, True, session_id, material_ids)
        return {
            'status': 'success',
            'not_found': True,
            'answer': "I couldn't find this information in your selected study materials.",
            'sources': [],
            'can_fallback_external': allow_external,
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

    if mode == "ask":
        system_p = (
            "You are an expert AI Tutor inside EduMi AI Study Workspace. "
            "Answer the student's question using ONLY the provided study material sources. "
            "Cite source titles and page numbers like [Title, Page X] for every fact."
        )
        user_p = f"STUDY MATERIALS CONTEXT:\n{context_str}\n\nSTUDENT QUESTION: {prompt}"

        answer = call_phi_llm(user_p, system_p)
        if not answer:
            answer = generate_fallback_ask(prompt, chunks, materials)

        s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
        return {
            'status': 'success',
            'mode': 'ask',
            'answer': answer,
            'sources': unique_sources,
            'not_found': False,
            'session_id': s_id
        }

    elif mode == "explain":
        level_instructions = {
            'simple': "Explain in simple, beginner-friendly terms with easy analogies.",
            'detailed': "Provide a thorough academic breakdown with clear step-by-step principles.",
            'exam': "Explain at an exam level, highlighting key terms, definitions, formulas, and potential exam questions."
        }
        level_str = level_instructions.get(explain_level, level_instructions['detailed'])

        system_p = f"You are an AI Study Assistant. {level_str} Ground your explanation in the provided materials and cite sources like [Title, Page X]."
        user_p = f"STUDY MATERIALS CONTEXT:\n{context_str}\n\nEXPLAIN TOPIC: {prompt or 'Core topics in these materials'}"

        answer = call_phi_llm(user_p, system_p)
        if not answer:
            answer = generate_fallback_explain(prompt, explain_level, chunks, materials)

        s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
        return {
            'status': 'success',
            'mode': 'explain',
            'explain_level': explain_level,
            'answer': answer,
            'sources': unique_sources,
            'not_found': False,
            'session_id': s_id
        }

    elif mode == "summarize":
        system_p = (
            "You are an academic summarization engine. Create a structured summary from the provided study materials. "
            "Include sections for: 1. Key Concepts, 2. Important Definitions, 3. Core Formulas / Rules, 4. Practical Examples, 5. Exam Focus Points."
        )
        user_p = f"STUDY MATERIALS CONTEXT:\n{context_str}\n\nSUMMARIZE REQUEST: {prompt or 'Summarize selected resources'}"

        answer = call_phi_llm(user_p, system_p)
        if not answer:
            answer = generate_fallback_summary(chunks, materials)

        s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
        return {
            'status': 'success',
            'mode': 'summarize',
            'answer': answer,
            'sources': unique_sources,
            'not_found': False,
            'session_id': s_id
        }

    elif mode == "quiz":
        quiz_data = generate_quiz_engine_data(chunks, materials)
        s_id = log_rag_query(user, mode, prompt, f"Generated {len(quiz_data)} quiz questions", len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
        return {
            'status': 'success',
            'mode': 'quiz',
            'quiz': quiz_data,
            'sources': unique_sources,
            'not_found': False,
            'session_id': s_id
        }

    elif mode == "revision":
        revision_data = generate_revision_engine_data(chunks, materials)
        s_id = log_rag_query(user, mode, prompt, "Generated revision flashcards", len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
        return {
            'status': 'success',
            'mode': 'revision',
            'revision': revision_data,
            'sources': unique_sources,
            'not_found': False,
            'session_id': s_id
        }

    return {'status': 'error', 'message': f'Invalid mode: {mode}'}


def run_rag_workspace_pipeline_stream(user, material_ids, prompt="", mode="ask", explain_level="detailed", strict_mode=True, allow_external=False, session_id=None):
    """
    Streaming variant of run_rag_workspace_pipeline emitting SSE text frames.
    """
    def _frame(payload):
        return payload

    materials = StudyMaterial.objects.filter(id__in=material_ids, is_published=True)
    if not materials.exists():
        yield _frame({'type': 'error', 'message': 'No study materials selected.', 'not_found': True})
        yield _frame({'type': 'done', 'status': 'error', 'answer': 'Please select at least one study resource to start an AI study session.', 'sources': []})
        return

    chunks = retrieve_source_chunks(material_ids, prompt, top_k=6)
    max_score = max([c['score'] for c in chunks]) if chunks else 0.0

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

    if strict_mode and (not chunks or (prompt and max_score < 0.12 and mode in ['ask', 'explain'])):
        msg = "I couldn't find this information in your selected study materials."
        s_id = log_rag_query(user, mode, prompt, msg, 0, [], strict_mode, True, session_id, material_ids)
        yield _frame({'type': 'meta', 'status': 'success', 'not_found': True, 'mode': mode, 'session_id': s_id})
        yield _frame({'type': 'done', 'status': 'success', 'not_found': True, 'answer': msg, 'sources': [], 'mode': mode, 'session_id': s_id})
        return

    if mode in ('quiz', 'revision'):
        result_payload = None
        if mode == 'quiz':
            quiz_data = generate_quiz_engine_data(chunks, materials)
            s_id = log_rag_query(user, mode, prompt, f"Generated {len(quiz_data)} quiz questions", len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
            result_payload = {'status': 'success', 'mode': 'quiz', 'quiz': quiz_data, 'sources': unique_sources, 'not_found': False, 'session_id': s_id}
        else:
            revision_data = generate_revision_engine_data(chunks, materials)
            s_id = log_rag_query(user, mode, prompt, "Generated revision flashcards", len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
            result_payload = {'status': 'success', 'mode': 'revision', 'revision': revision_data, 'sources': unique_sources, 'not_found': False, 'session_id': s_id}
        yield _frame({'type': 'meta', **result_payload})
        yield _frame({'type': 'done', **result_payload})
        return

    level_instructions = {
        'simple': "Explain in simple, beginner-friendly terms with easy analogies.",
        'detailed': "Provide a thorough academic breakdown with clear step-by-step principles.",
        'exam': "Explain at an exam level, highlighting key terms, definitions, formulas, and potential exam questions."
    }

    system_p = user_p = None
    if mode == "ask":
        system_p = (
            "You are an AI Tutor inside EduMi AI Study Workspace. "
            "Answer the student's question using ONLY the provided study material sources. "
            "Cite source titles and page numbers like [Title, Page X] for every fact."
        )
        user_p = f"STUDY MATERIALS CONTEXT:\n{context_str}\n\nSTUDENT QUESTION: {prompt}"
    elif mode == "explain":
        level_str = level_instructions.get(explain_level, level_instructions['detailed'])
        system_p = f"You are an AI Study Assistant. {level_str} Ground your explanation in the provided materials and cite sources like [Title, Page X]."
        user_p = f"STUDY MATERIALS CONTEXT:\n{context_str}\n\nEXPLAIN TOPIC: {prompt or 'Core topics in these materials'}"
    elif mode == "summarize":
        system_p = (
            "You are an academic summarization engine. Create a structured summary from the provided study materials. "
            "Include sections for: 1. Key Concepts, 2. Important Definitions, 3. Core Formulas / Rules, 4. Practical Examples, 5. Exam Focus Points."
        )
        user_p = f"STUDY MATERIALS CONTEXT:\n{context_str}\n\nSUMMARIZE REQUEST: {prompt or 'Summarize selected resources'}"

    yield _frame({'type': 'meta', 'status': 'success', 'not_found': False, 'mode': mode, 'sources_count': len(unique_sources)})

    collected = []
    fallback_emitted = False
    token_count = 0

    for delta in call_phi_llm_stream(user_p, system_prompt=system_p):
        collected.append(delta)
        token_count += 1
        yield _frame({'type': 'token', 'delta': delta})

    answer = "".join(collected).strip()
    if not answer:
        fallback_emitted = True
        if mode == "ask":
            answer = generate_fallback_ask(prompt, chunks, materials)
        elif mode == "explain":
            answer = generate_fallback_explain(prompt, explain_level, chunks, materials)
        else:
            answer = generate_fallback_summary(chunks, materials)
        for i in range(0, len(answer), 6):
            yield _frame({'type': 'token', 'delta': answer[i:i+6]})

    s_id = log_rag_query(user, mode, prompt, answer, len(chunks), unique_sources, strict_mode, False, session_id, material_ids)
    yield _frame({
        'type': 'done',
        'status': 'success',
        'mode': mode,
        'explain_level': explain_level if mode == 'explain' else None,
        'answer': answer,
        'sources': unique_sources,
        'not_found': False,
        'fallback_used': fallback_emitted,
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
    session = None
    try:
        if session_id:
            session = RagSession.objects.filter(id=session_id, user=user).first()
        
        if not session and user.is_authenticated:
            session = RagSession.objects.create(
                user=user,
                title=prompt[:40] if prompt else "AI Study Session",
                strict_mode=strict_mode,
                active_mode=mode
            )

        if session:
            # Update session title if default
            if session.title in ("AI Study Session", "New Chat", "New AI Study Session") and prompt:
                session.title = prompt[:40] + ("..." if len(prompt) > 40 else "")
            session.updated_at = timezone.now()
            session.active_mode = mode
            session.save(update_fields=['title', 'updated_at', 'active_mode'])

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
