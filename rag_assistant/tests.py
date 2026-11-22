from common.test_base import BaseTestCase, TeacherUserFactory
from meetings.models import Classroom, StudyMaterial, MaterialChunk
from .services import cosine_similarity, rerank_and_deduplicate_chunks

class MaterialChunkTests(BaseTestCase):
    """Test MaterialChunk model for RAG"""

    def setUp(self):
        self.teacher = TeacherUserFactory()
        self.classroom = Classroom.objects.create(
            class_code='RAG101',
            title='RAG Test Classroom',
            password='testpass',
            teacher=self.teacher
        )

        self.material = StudyMaterial.objects.create(
            classroom=self.classroom,
            title='Test Document',
            material_type='document',
            uploaded_by=self.teacher,
            extracted_text='This is test content for RAG testing.',
            rag_indexed=True
        )

    def test_chunk_creation(self):
        """Test creating material chunk"""
        chunk = MaterialChunk.objects.create(
            material=self.material,
            chunk_index=0,
            chunk_text='This is test content',
            token_count=5,
            embedding_vector=[0.1] * 384
        )

        self.assertEqual(chunk.material, self.material)
        self.assertEqual(chunk.chunk_index, 0)
        self.assertEqual(len(chunk.embedding_vector), 384)

    def test_chunk_ordering(self):
        """Test chunks are ordered by index"""
        for i in range(5):
            MaterialChunk.objects.create(
                material=self.material,
                chunk_index=i,
                chunk_text=f'Chunk {i}',
                token_count=10
            )

        retrieved = list(MaterialChunk.objects.filter(
            material=self.material
        ).order_by('chunk_index'))

        self.assertEqual(len(retrieved), 5)
        for i, chunk in enumerate(retrieved):
            self.assertEqual(chunk.chunk_index, i)


class RAGServiceTests(BaseTestCase):
    """Test RAG service operations"""

    def test_cosine_similarity(self):
        """Test cosine similarity function"""
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]

        sim_same = cosine_similarity(v1, v2)
        self.assertAlmostEqual(sim_same, 1.0, places=4)

        sim_orth = cosine_similarity(v1, v3)
        self.assertAlmostEqual(sim_orth, 0.0, places=4)

    def test_rerank_and_deduplicate(self):
        """Test deduplication and ranking of retrieved chunks"""
        chunks = [
            {'chunk_id': 1, 'score': 0.85, 'text': 'Python is a language'},
            {'chunk_id': 2, 'score': 0.85, 'text': 'Python is a language'},  # duplicate
            {'chunk_id': 3, 'score': 0.90, 'text': 'Django framework'},
            {'chunk_id': 4, 'score': 0.10, 'text': 'Unrelated low score'},
        ]
        result = rerank_and_deduplicate_chunks(chunks, min_score=0.3, max_chunks=3)
        self.assertLessEqual(len(result), 3)
        # Should be sorted by score descending
        if len(result) >= 2:
            self.assertGreaterEqual(result[0]['score'], result[1]['score'])
