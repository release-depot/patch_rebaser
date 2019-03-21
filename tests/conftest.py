#! /usr/bin/env python
"""Base fixtures for unit tests"""

from mock import Mock
import pytest


@pytest.fixture
def mock_repo():
    repo_mock = Mock()
    repo_mock.attach_mock(Mock(), 'git')
    return repo_mock
