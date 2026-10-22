import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import requests
from src.utils.gemini_embeddings import encode
from src.ingestion.profile import ingestion_profile

CONFIG = {'EMBEDDING_BACKEND': 'gemini', 'GEMINI_API_KEY': 'unit-test-key',
          'GEMINI_EMBEDDING_MODEL': 'gemini-embedding-2', 'GEMINI_EMBEDDING_DIMENSION': '768',
          'PINECONE_NAMESPACE': 'gemini-unit', 'PIPECONE_PDF_CHUNK_INDEX': 'gemini-index'}


def response(values=None, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = {'embedding': {'values': values if values is not None else [1.] * 768}}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


class GeminiEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict('os.environ', CONFIG)
        self.config.start()
        self.addCleanup(self.config.stop)

    def test_separate_chunks_have_separate_vectors_and_are_normalized(self):
        with patch('src.utils.gemini_embeddings.requests.post', side_effect=[response(),response([2.]*768)]) as post:
            vectors = encode(['chunk one', 'chunk two'])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(vectors.shape, (2, 768))
        self.assertTrue(np.allclose(np.linalg.norm(vectors, axis=1), 1))
        first = post.call_args_list[0]
        self.assertIn('title: none | text: chunk one', first.kwargs['json']['content']['parts'][0]['text'])
        self.assertEqual(first.kwargs['json']['outputDimensionality'],768)
        self.assertNotIn('taskType', first.kwargs['json'])
        self.assertNotIn('unit-test-key', first.args[0])
        self.assertEqual(first.kwargs['headers']['x-goog-api-key'], 'unit-test-key')

    def test_query_uses_retrieval_prefix(self):
        with patch('src.utils.gemini_embeddings.requests.post', return_value=response()) as post:
            encode(['question'], 'RETRIEVAL_QUERY')
        self.assertEqual(post.call_args.kwargs['json']['content']['parts'][0]['text'],
                         'task: search result | query: question')

    def test_001_uses_task_type_instead_of_prefix(self):
        with patch.dict('os.environ', {'GEMINI_EMBEDDING_MODEL':'gemini-embedding-001'}), patch('src.utils.gemini_embeddings.requests.post', return_value=response()) as post:
            encode(['question'], 'RETRIEVAL_QUERY')
        self.assertEqual(post.call_args.kwargs['json']['taskType'], 'RETRIEVAL_QUERY')
        self.assertEqual(post.call_args.kwargs['json']['content']['parts'][0]['text'], 'question')

    def test_retry_rate_limit_but_not_invalid_key(self):
        with patch('src.utils.gemini_embeddings.requests.post', side_effect=[response(status=429),response()]) as post, patch('src.utils.gemini_embeddings.time.sleep'):
            self.assertEqual(encode(['text']).shape, (1,768))
            self.assertEqual(post.call_count,2)
        with patch('src.utils.gemini_embeddings.requests.post', return_value=response(status=403)) as post:
            with self.assertRaises(requests.HTTPError):
                encode(['text'])
            self.assertEqual(post.call_count,1)

    def test_reject_wrong_dimension_and_zero_vectors(self):
        for values in [[1.]*384, [0.]*768, [float('nan')]*768]:
            with patch('src.utils.gemini_embeddings.requests.post', return_value=response(values)):
                with self.assertRaises(ValueError):
                    encode(['text'])

    def test_empty_batch_and_missing_key_never_send_requests(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY':''}), patch('src.utils.gemini_embeddings.requests.post') as post:
            self.assertEqual(encode([]).shape,(0,768))
            with self.assertRaisesRegex(ValueError,'GEMINI_API_KEY'):
                encode(['text'])
            post.assert_not_called()

    def test_profile_changes_for_new_backend_namespace_or_dimension(self):
        gemini = ingestion_profile()
        self.assertLessEqual(len(gemini),50)
        with patch.dict('os.environ', {'EMBEDDING_BACKEND':'huggingface'}):
            self.assertNotEqual(ingestion_profile(), gemini)
        for setting,value in [('PINECONE_NAMESPACE','other'),('GEMINI_EMBEDDING_DIMENSION','1536')]:
            with patch.dict('os.environ', {setting:value}):
                self.assertNotEqual(ingestion_profile(), gemini)

    def test_wrong_pinecone_dimension_fails_before_embedding_request(self):
        from src.utils.pinecone_service import upsert_chunks
        index = MagicMock()
        index.describe_index_stats.return_value = {'dimension':384}
        with patch('src.utils.pinecone_service.get_pipecone_chunk_index',return_value=index), patch('src.utils.pinecone_service.get_embeddings') as embed:
            with self.assertRaisesRegex(ValueError,'dimension'):
                upsert_chunks([1],['text'],'1',1)
            embed.assert_not_called()
            index.upsert.assert_not_called()
