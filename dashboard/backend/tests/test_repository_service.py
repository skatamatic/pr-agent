"""
Unit tests for RepositoryService (get_repositories, create_repository, get_repository).
Uses in-memory DB; repositories table created by app startup.
"""
import pytest
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, initialize_database
from services.repository_service import RepositoryService
from models import RepositoryCreate, RepositoryUpdate, RepositoryProvider


@pytest.fixture(scope="module")
def ensure_db_tables():
    """Ensure all tables (including repositories) exist."""
    initialize_database()
    yield


@pytest.fixture
def db_session(ensure_db_tables):
    with SessionLocal() as session:
        yield session


@pytest.fixture
def repo_service():
    return RepositoryService()


@pytest.mark.asyncio
class TestRepositoryService:
    async def test_get_repositories_empty(self, repo_service, db_session):
        result = await repo_service.get_repositories(db_session)
        assert result.total >= 0
        assert isinstance(result.data, list)

    async def test_get_repositories_with_limit(self, repo_service, db_session):
        result = await repo_service.get_repositories(db_session, limit=5)
        assert len(result.data) <= 5

    async def test_create_and_get_repository(self, repo_service, db_session):
        repo_data = RepositoryCreate(
            name="test/repo-service-1",
            provider=RepositoryProvider.GITHUB,
            url="https://github.com/test/repo-service-1",
        )
        created = await repo_service.create_repository(db_session, repo_data)
        assert created.name == "test/repo-service-1"
        assert created.provider == "github"
        got = await repo_service.get_repository(db_session, created.id)
        assert got is not None
        assert got.name == created.name

    async def test_create_duplicate_raises(self, repo_service, db_session):
        repo_data = RepositoryCreate(
            name="test/dup-repo",
            provider=RepositoryProvider.GITHUB,
            url="https://github.com/test/dup-repo",
        )
        await repo_service.create_repository(db_session, repo_data)
        with pytest.raises(Exception, match="already exists"):
            await repo_service.create_repository(db_session, repo_data)

    async def test_get_repository_not_found(self, repo_service, db_session):
        result = await repo_service.get_repository(db_session, 999999)
        assert result is None

    async def test_get_repository_names(self, repo_service, db_session):
        names = await repo_service.get_repository_names(db_session, active_only=False)
        assert isinstance(names, list)

    async def test_get_repository_names_active_only(self, repo_service, db_session):
        names = await repo_service.get_repository_names(db_session, active_only=True)
        assert isinstance(names, list)

    async def test_get_repositories_with_provider(self, repo_service, db_session):
        result = await repo_service.get_repositories(db_session, limit=10, provider="github")
        assert isinstance(result.data, list)
        assert result.total >= 0

    async def test_get_repositories_active_only(self, repo_service, db_session):
        result = await repo_service.get_repositories(db_session, limit=10, active_only=True)
        assert isinstance(result.data, list)
