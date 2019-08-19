#! /usr/bin/env python
"""Base fixtures for unit tests"""

import os

from mock import Mock, patch
import pytest


@pytest.fixture
def mock_repo():
    repo_mock = Mock()
    repo_mock.attach_mock(Mock(), 'git')
    return repo_mock


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setitem(os.environ, 'DLRN_USER', 'TEST_USER')
    monkeypatch.setitem(os.environ, 'DLRN_SOURCEDIR', 'TEST_SOURCEDIR')
    monkeypatch.setitem(os.environ, 'DLRN_SOURCE_COMMIT', '123456a')
    monkeypatch.setitem(os.environ, 'DLRN_DISTROINFO_REPO', 'TEST_DI_REPO')
    monkeypatch.setitem(os.environ, 'DLRN_PACKAGE_NAME', 'TEST_PACKAGE')
    monkeypatch.setitem(os.environ, 'PATCHES_BRANCH', 'test-patches')


@pytest.fixture
def mock_config(datadir):
    patcher = patch('os.path.realpath',
                    return_value=str(datadir/'test_config.ini'))
    patcher.start()
    yield
    patcher.stop()


@pytest.fixture
def mock_config_with_pkgs_to_process(datadir):
    patcher = patch('os.path.realpath',
                    return_value=str(datadir/'pkgs_to_process_config.ini'))
    patcher.start()
    yield
    patcher.stop()


@pytest.fixture
def mock_config_with_create_patches_branch(datadir):
    patcher = patch('os.path.realpath',
                    return_value=str(datadir/'test_config_create_branch.ini'))
    patcher.start()
    yield
    patcher.stop()
