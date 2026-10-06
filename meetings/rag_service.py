"""
meetings/rag_service.py
Core Retrieval-Augmented Generation (RAG) Service for EduMi AI Study Workspace.
Connects vector/chunk text search with LLM API & Ollama fallback
and formats source-grounded answers with citations, quizzes, summaries, and revision modes.
"""

from rag_workspace.services import (
    retrieve_source_chunks as retrieve_relevant_chunks,
    call_phi_llm as call_external_llm,
    run_rag_workspace_pipeline as execute_rag_pipeline,
    generate_fallback_ask as generate_local_grounded_answer,
    generate_fallback_explain as generate_local_explain_answer,
    generate_fallback_summary as generate_local_summary,
    generate_quiz_engine_data as generate_quiz_questions,
    generate_revision_engine_data as generate_revision_cards
)

__all__ = [
    'retrieve_relevant_chunks',
    'call_external_llm',
    'execute_rag_pipeline',
    'generate_local_grounded_answer',
    'generate_local_explain_answer',
    'generate_local_summary',
    'generate_quiz_questions',
    'generate_revision_cards',
]
