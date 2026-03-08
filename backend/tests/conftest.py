"""
Shared pytest fixtures for Forensic Council backend tests.
"""
import pytest


@pytest.fixture
def sample_session_id() -> str:
    return "test-session-12345"


@pytest.fixture
def sample_case_id() -> str:
    return "CASE-1697000000"


@pytest.fixture
def sample_investigator_id() -> str:
    return "REQ-12345"
