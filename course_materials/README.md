# 📚 Course Materials (`course_materials`) — Academic Digital Library & RAG Ingestion

<details open>
<summary><b>1. Core Purpose</b></summary>
The `course_materials` app provides a centralized academic digital library and curriculum document management repository. It handles syllabi, lecture slides, textbooks, lecture notes, and supplementary files organized by curriculum units, while preparing and tracking document embeddings for semantic RAG (Retrieval-Augmented Generation) search.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>
Separating document and study resource management from the real-time meeting and classroom scheduling engine decouples large file I/O and text extraction workflows from real-time WebRTC logic.

Key architecture points:
1. **Curriculum Hierarchy:** Materials are grouped under `MaterialUnit` topic folders linked to an academic classroom.
2. **Multi-Format Support:** Accommodates PDFs, presentation slides, markdown/plain text notes, recordings, e-books, and external reference links.
3. **Automated Vector Chunking Lifecycle:** Manages `MaterialChunk` slices (500 tokens with 50-token overlap), storing dense vectors, page numbers, and indexing state (`rag_indexed`, `rag_indexed_at`, `rag_metadata`) directly consumed by `rag_assistant`.
4. **Resilient Data Compatibility:** Configured with `db_table` preservation to guarantee zero database migration disruption.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Uploading Resources:** Teachers upload study documents via the classroom materials tab, specifying unit, description, and publishing visibility.
- **Student Bookmarking:** Students can bookmark important references for quick retrieval through `MaterialBookmark`.
- **RAG Preprocessing:** On upload, document texts are parsed, chunked into `MaterialChunk` records, and embedded for instantaneous semantic search in `rag_assistant`.
</details>

<details>
<summary><b>4. System Integrations</b></summary>

- **Academics / Classrooms (`academics` & `meetings`):** Associates study resources with enrolled courses and units.
- **RAG Assistant (`rag_assistant`):** Supplies chunked text and metadata for semantic similarity search, quiz generation, and AI explanations.
- **Common App:** Leverages file validators and compression helpers for secure, lightweight document storage.
</details>

<details>
<summary><b>5. Key Models Breakdown</b></summary>

- `MaterialUnit`: Curriculum topic folder / chapter organizing course resources.
- `StudyMaterial`: Core resource model storing files, URLs, plain notes, download counters, and RAG status.
- `MaterialChunk`: Segmented document slice storing token counts, page numbers, and vector embeddings.
- `MaterialBookmark`: Student bookmark association for quick library access.
</details>
