# 🤖 RAG Assistant (`rag_assistant`) — AI Study Assistant & Knowledge Engine

<details open>
<summary><b>1. Core Purpose</b></summary>
The `rag_assistant` app is an integrated Retrieval-Augmented Generation (RAG) educational intelligence engine for EduMi. It enables students to query course documents, textbook chapters, lecture slides, and teacher notes to receive instant, hallucination-free contextual answers with cited page references.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>
Standard Large Language Models (LLMs) hallucinate and lack knowledge of private classroom syllabi and textbooks. The RAG architecture bridges this gap:
1. **Document Ingestion & Chunking:** When teachers upload lecture PDFs or notes to `StudyMaterial` (managed via `course_materials`), the text is extracted and partitioned into 500-token semantic chunks with a 50-token overlap to maintain contextual continuity across boundaries.
2. **Dense Vector Embeddings:** Each chunk is converted into a 768-dimensional dense vector embedding via `nomic-embed-text` (or OpenAI embeddings) and stored in `MaterialChunk`.
3. **Semantic Cosine Retrieval:** When a student submits a question, the query vector is compared against document chunk embeddings using Cosine Similarity:
   $$\text{Sim}(\vec{q}, \vec{c}_i) = \frac{\vec{q} \cdot \vec{c}_i}{\|\vec{q}\| \|\vec{c}_i\|}$$
   The top-$K$ most relevant passages are retrieved and injected into the LLM prompt as factual ground truth.
4. **Flexible LLM Backend:** Connects to local **Ollama** instances (`phi:latest`, `llama3:8b`, `mistral:7b`), Cloudflare Workers AI, or OpenAI (`gpt-4o-mini`) via environment configuration.
</details>

<details open>
<summary><b>3. Five Specialized Educational Modes</b></summary>

| Mode | Pedagogical Objective | Prompt Behavior |
|---|---|---|
| **Ask Mode** | Direct Fact Retrieval | Provides precise answers strictly grounded in the uploaded materials with cited page numbers. |
| **Explain Mode** | Conceptual Clarity | Breaks down difficult engineering, scientific, or mathematical formulas into beginner-friendly analogies. |
| **Summarize Mode** | Executive Review | Condenses multi-page lecture notes or chapters into bulleted high-yield study outlines. |
| **Practice / Quiz Mode** | Knowledge Retention | Formulates multiple-choice and conceptual practice questions based on the retrieved document context. |
| **Study / Revision Mode** | Exam Preparation | Produces high-density flashcards, key definitions, and formula cheat-sheets. |
</details>

<details open>
<summary><b>4. Fault Tolerance & Circuit Breaker</b></summary>

### 30-Second Circuit Breaker (`_EMBEDDING_OFFLINE_UNTIL`)
If the local Ollama instance or external AI API experiences downtime or network timeouts:
- The service activates a 30-second circuit breaker.
- Subsequent requests fail-fast with a user-friendly notice rather than hanging background worker threads and causing HTTP 504 gateway timeouts.
- Automatically resets and re-tests the AI endpoint once the cooling window expires.
</details>

<details>
<summary><b>5. Usage Instructions</b></summary>

- **Uploading Study Materials:** Teachers upload course PDFs or notes in the Classroom detail view under the "Materials" tab (powered by `course_materials`).
- **Starting an AI Session:** Students navigate to `/rag/` or click "Ask AI" in any enrolled classroom to start a `RagSession`.
- **Switching Modes:** Use the interactive dropdown to switch between Ask, Explain, Summarize, Practice, and Study modes.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `RagSession` (multi-turn conversation container), `RagChatMessage` (individual user/assistant message history), and `RagQueryLog` (telemetry and latency logging).
- `services.py`: Core RAG orchestration: document embedding generation (`get_nomic_embedding`), prompt synthesis, cosine retrieval, and circuit breaker logic.
- `views.py`: API endpoints for starting sessions, streaming chat completions, and querying indexed materials.
- `urls.py`: URL routing for RAG assistant endpoints (`/rag/`).
</details>
