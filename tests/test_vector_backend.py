import unittest

from app.services.vector_store import SimpleKeywordVectorBackend, VectorDocument


class VectorBackendTestCase(unittest.TestCase):
    def test_simple_keyword_vector_scores_relevant_document_higher(self):
        backend = SimpleKeywordVectorBackend()
        matches = backend.score_documents(
            '订单风控规则',
            [
                VectorDocument(document_id='doc_1', text='订单风控规则必须通过统一规则引擎接入', metadata={}),
                VectorDocument(document_id='doc_2', text='用户登录界面样式调整', metadata={}),
            ],
        )
        self.assertEqual(matches[0].document_id, 'doc_1')
        self.assertGreater(matches[0].score, matches[1].score)


if __name__ == '__main__':
    unittest.main()
