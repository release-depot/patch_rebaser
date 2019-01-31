#!/usr/bin/env python
# -*- coding: utf-8 -*-

from unittest.mock import Mock
import pytest

from patch_rebaser.patch_rebaser import (
    find_patches_branch,
    parse_distro_info_path
)


def test_find_patches_branch():
    branches = {
        "xxxx-154.23-zzzz-1": "xxxx-154.23-patches",
        "xxxx-90.0-zzzz-1-trunk": "xxxx-90.0-trunk-patches",
        "xxxx-1.0-zzzz-1": "xxxx-1.0-patches"
    }

    def mock_branch_exists(branch, remote):
        if branch in branches.values():
            return True
        else:
            return False

    mock_repo = Mock()
    mock_repo.branch.exists = mock_branch_exists

    for distgit, patches in branches.items():
        assert patches == find_patches_branch(mock_repo, "", distgit)


def test_parse_distro_info_path():
    # Result form: file, path, remote boolean
    data = {
        "/home/dlrn/di/test.yaml": ("test.yaml", "/home/dlrn/di", False),
        "https://example.com/info/info.yml": ("info.yml",
                                              "https://example.com/info",
                                              True),
    }

    for path, result in data.items():
        assert parse_distro_info_path(path) == result
