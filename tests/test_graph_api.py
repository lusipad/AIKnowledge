import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_db
from app.models import KnowledgeItem
from app.services.bootstrap import seed_default_profiles
from tests.support import build_test_app


class GraphApiTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            'sqlite://',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)

        database = self.SessionTesting()
        try:
            seed_default_profiles(database)
            database.add_all(
                [
                    KnowledgeItem(
                        knowledge_id='kn_repo_rule',
                        tenant_id='tenant-demo',
                        team_id='team-demo',
                        scope_type='repo',
                        scope_id='repo-a',
                        knowledge_type='rule',
                        memory_type='semantic',
                        title='仓库 A 风控规则',
                        content={'summary': 'repo-a risk rule'},
                        acl={'owners': ['user-reviewer'], 'reviewers': ['role:reviewer'], 'viewers': ['role:viewer']},
                        status='active',
                        created_by='test-suite',
                    ),
                    KnowledgeItem(
                        knowledge_id='kn_repo_case',
                        tenant_id='tenant-demo',
                        team_id='team-demo',
                        scope_type='repo',
                        scope_id='repo-b',
                        knowledge_type='case',
                        memory_type='episodic',
                        title='仓库 B 复盘案例',
                        content={'summary': 'repo-b case'},
                        acl={'owners': ['user-reviewer'], 'reviewers': ['role:reviewer'], 'viewers': ['role:viewer']},
                        status='active',
                        created_by='test-suite',
                    ),
                    KnowledgeItem(
                        knowledge_id='kn_hidden_rule',
                        tenant_id='tenant-demo',
                        team_id='team-demo',
                        scope_type='repo',
                        scope_id='repo-a',
                        knowledge_type='rule',
                        memory_type='semantic',
                        title='隐藏规则',
                        content={'summary': 'hidden rule'},
                        acl={'owners': ['secret-user'], 'reviewers': [], 'viewers': ['secret-user']},
                        status='active',
                        created_by='test-suite',
                    ),
                ]
            )
            database.commit()
        finally:
            database.close()

        def override_get_db():
            database = self.SessionTesting()
            try:
                yield database
            finally:
                database.close()

        self.app = build_test_app()
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_create_relation_and_fetch_knowledge_graph(self):
        headers = {
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-demo',
            'X-User-Id': 'user-reviewer',
            'X-User-Role': 'reviewer',
        }
        create_response = self.client.post(
            '/api/v1/graph/relations',
            json={
                'knowledge_id': 'kn_repo_rule',
                'related_knowledge_id': 'kn_repo_case',
                'relation_type': 'supersedes',
                'weight': 0.9,
                'detail': {'reason': 'repo-b case promoted to repo-wide rule'},
            },
            headers=headers,
        )
        self.assertEqual(create_response.status_code, 200)
        payload = create_response.json()['data']
        self.assertEqual(payload['repo_id'], 'repo-a')
        self.assertEqual(payload['related_repo_id'], 'repo-b')
        self.assertEqual(payload['relation_type'], 'supersedes')

        graph_response = self.client.get('/api/v1/graph/knowledge/kn_repo_rule', headers=headers)
        self.assertEqual(graph_response.status_code, 200)
        graph_payload = graph_response.json()['data']
        self.assertEqual(graph_payload['knowledge']['knowledge_id'], 'kn_repo_rule')
        self.assertEqual(len(graph_payload['relations']), 1)
        self.assertEqual(graph_payload['relations'][0]['direction'], 'outbound')
        self.assertEqual(graph_payload['relations'][0]['counterpart']['knowledge_id'], 'kn_repo_case')

    def test_repo_knowledge_map_hides_unviewable_nodes(self):
        headers = {
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-demo',
            'X-User-Id': 'user-reviewer',
            'X-User-Role': 'reviewer',
        }
        self.client.post(
            '/api/v1/graph/relations',
            json={
                'knowledge_id': 'kn_repo_rule',
                'related_knowledge_id': 'kn_repo_case',
                'relation_type': 'related_to',
            },
            headers=headers,
        )
        hidden_response = self.client.post(
            '/api/v1/graph/relations',
            json={
                'knowledge_id': 'kn_repo_rule',
                'related_knowledge_id': 'kn_hidden_rule',
                'relation_type': 'implements_rule',
            },
            headers=headers,
        )
        self.assertEqual(hidden_response.status_code, 404)

        viewer_headers = {
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-demo',
            'X-User-Id': 'viewer-user',
            'X-User-Role': 'viewer',
        }
        map_response = self.client.get('/api/v1/graph/repos/repo-a/knowledge-map', headers=viewer_headers)
        self.assertEqual(map_response.status_code, 200)
        map_payload = map_response.json()['data']
        self.assertEqual({item['knowledge_id'] for item in map_payload['nodes']}, {'kn_repo_rule', 'kn_repo_case'})
        self.assertEqual(len(map_payload['relations']), 1)
        self.assertEqual(map_payload['relations'][0]['related_repo_id'], 'repo-b')

    def test_graph_write_requires_reviewer_role(self):
        response = self.client.post(
            '/api/v1/graph/relations',
            json={
                'knowledge_id': 'kn_repo_rule',
                'related_knowledge_id': 'kn_repo_case',
                'relation_type': 'related_to',
            },
            headers={
                'X-Tenant-Id': 'tenant-demo',
                'X-Team-Id': 'team-demo',
                'X-User-Id': 'viewer-user',
                'X-User-Role': 'viewer',
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_graph_scope_hides_foreign_team_relations(self):
        reviewer_headers = {
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-demo',
            'X-User-Id': 'user-reviewer',
            'X-User-Role': 'reviewer',
        }
        create_response = self.client.post(
            '/api/v1/graph/relations',
            json={
                'knowledge_id': 'kn_repo_rule',
                'related_knowledge_id': 'kn_repo_case',
                'relation_type': 'same_incident_family',
            },
            headers=reviewer_headers,
        )
        self.assertEqual(create_response.status_code, 200)

        foreign_team_headers = {
            'X-Tenant-Id': 'tenant-demo',
            'X-Team-Id': 'team-other',
            'X-User-Id': 'viewer-other-team',
            'X-User-Role': 'viewer',
        }
        knowledge_response = self.client.get('/api/v1/graph/knowledge/kn_repo_rule', headers=foreign_team_headers)
        self.assertEqual(knowledge_response.status_code, 404)

        repo_map_response = self.client.get('/api/v1/graph/repos/repo-a/knowledge-map', headers=foreign_team_headers)
        self.assertEqual(repo_map_response.status_code, 200)
        self.assertEqual(repo_map_response.json()['data']['nodes'], [])
        self.assertEqual(repo_map_response.json()['data']['relations'], [])


if __name__ == '__main__':
    unittest.main()
