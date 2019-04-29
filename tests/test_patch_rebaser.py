#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time

from git_wrapper import exceptions
from mock import MagicMock, Mock
import pytest

import patch_rebaser
from patch_rebaser.patch_rebaser import (
    find_patches_branch,
    get_rebaser_config,
    main,
    parse_distro_info_path,
    Rebaser,
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


def test_update_remote_patches_branch_no_changes_with_remote(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN update_remote_patches_branch is called
    AND cherry_on_head_only returns false (indicating the local and remote
        branches have no differences)
    THEN tag.delete is called
    AND git.push is not called
    """
    mock_repo.branch.cherry_on_head_only.return_value = False

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)
    rebaser.update_remote_patches_branch()

    mock_repo.tag.delete.assert_called_once()
    assert mock_repo.git.push.called is False


def test_update_remote_patches_branch_with_dev_mode(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WITH dev_mode set to true
    WHEN update_remote_patches_branch is called
    THEN tag.delete is not called
    AND git.push is called with -n argument for dry-run
    """
    mock_repo.branch.cherry_on_head_only.return_value = True

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "2019", dev_mode=True)
    rebaser.update_remote_patches_branch()

    # Tag not deleted, and pushed with -n for dry-run
    assert mock_repo.tag.delete.called is False
    assert mock_repo.git.push.called is True

    expected = [(("-n", "my_remote", "private-rebaser-2019-previous"),),
                (("-nf", "my_remote", "my_branch"),)]
    assert mock_repo.git.push.call_args_list == expected


def test_update_remote_patches_branch_without_dev_mode(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WITH dev_mode set to false
    WHEN update_remote_patches_branch is called
    THEN tag.delete is not called
    AND git.push is called without -n
    """
    mock_repo.branch.cherry_on_head_only.return_value = True

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "2019", dev_mode=False)
    rebaser.update_remote_patches_branch()

    # Tag not deleted, and pushed without -n
    assert mock_repo.tag.delete.called is False
    assert mock_repo.git.push.called is True

    expected = [(("my_remote", "private-rebaser-2019-previous"),),
                (("-f", "my_remote", "my_branch"),)]
    assert mock_repo.git.push.call_args_list == expected


def test_perform_rebase(mock_repo):
    """
    GIVEN Rebaser initialized correctly including branch and commit
    WHEN perform_rebase is called
    THEN branch.rebase_to_hash is called
    WITH the same branch and commit
    """
    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)
    rebaser.perform_rebase()

    mock_repo.branch.rebase_to_hash.assert_called()
    mock_repo.branch.rebase_to_hash.assert_called_with(
        "my_branch", "my_commit"
    )


def test_perform_rebase_aborts_on_failure(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN rebase_to_hash fails with RebaseException
    THEN perform_rebase also raises RebaseException
    AND abort_rebase is called
    """
    mock_repo.branch.rebase_to_hash.side_effect = exceptions.RebaseException

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)

    with pytest.raises(exceptions.RebaseException):
        rebaser.perform_rebase()

    mock_repo.branch.abort_rebase.assert_called()


def test_rebase_and_update_remote(mock_repo, monkeypatch):
    """
    GIVEN Rebaser initialized correctly
    WHEN rebase_and_update_remote is called
    THEN a tag is created
    AND remote.fetch is called twice to catch remote updates during the rebase
    AND git.push is called
    """
    monkeypatch.setattr(time, 'sleep', lambda s: None)

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "2019", dev_mode=True)

    mock_repo.commit.same.return_value = True
    rebaser.rebase_and_update_remote()

    assert mock_repo.tag.create.call_count == 1
    assert mock_repo.remote.fetch.call_count == 2

    expected = [(("-n", "my_remote", "private-rebaser-2019-previous"),),
                (("-nf", "my_remote", "my_branch"),)]
    assert mock_repo.git.push.call_args_list == expected


def test_rebase_and_update_remote_success_after_retry(mock_repo, monkeypatch):
    """
    GIVEN Rebaser initialized correctly
    WHEN rebase_and_update_remote is called
    AND the remote changes once during the rebase
    THEN the tag gets created
    AND the previous tag gets deleted and re-created during the retry
    AND git.push is called
    """
    monkeypatch.setattr(time, 'sleep', lambda s: None)

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)

    mock_repo.commit.same.side_effect = [False, True]
    rebaser.rebase_and_update_remote()

    assert mock_repo.tag.create.call_count == 2
    assert mock_repo.remote.fetch.call_count == 4
    mock_repo.tag.delete.assert_called_once()

    mock_repo.git.push.assert_called()


def test_rebase_and_update_remote_stop_after_retries(mock_repo, monkeypatch):
    """
    GIVEN Rebaser initialized correctly
    WHEN rebase_and_update_remote is called
    AND the remote keeps changing during the rebase
    THEN the tag gets updated (recreated) during each attempt
    AND git.push is not called in the end
    """
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    monkeypatch.setattr(Rebaser, 'update_remote_patches_branch',
                        lambda s: None)

    mock_repo.commit.same.return_value = False

    def retry(max_retries):
        rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                          "my_tstamp", True, max_retries)
        rebaser.rebase_and_update_remote()

        assert mock_repo.tag.create.call_count == 1 + max_retries
        assert mock_repo.remote.fetch.call_count == 2 + 2 * max_retries
        assert mock_repo.tag.delete.call_count == max_retries
        mock_repo.git.push.assert_not_called()

        mock_repo.reset_mock()

    retry(0)  # Only ever try once
    retry(1)
    retry(2)


def test_rebase_and_update_remote_fails_next_rebase(mock_repo, monkeypatch):
    """
    GIVEN Rebaser initialized correctly
    WHEN rebase_and_update_remote is called
    AND the remote changed once during the rebase
    AND the rebase fails with RebaseException during the second rebase
    THEN a RebaseException is raised
    AND git.push is not called
    """
    monkeypatch.setattr(time, 'sleep', lambda s: None)

    mock_repo.branch.rebase_to_hash.side_effect = [None,
                                                   exceptions.RebaseException]
    mock_repo.commit.same.side_effect = [False, True]

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)
    with pytest.raises(exceptions.RebaseException):
        rebaser.rebase_and_update_remote()

    assert mock_repo.remote.fetch.call_count == 3

    assert mock_repo.tag.create.call_count == 2
    mock_repo.tag.delete.assert_called_once()
    mock_repo.git.push.assert_not_called()


def test_get_rebaser_config_with_fallback_value(mock_config):
    """
    GIVEN a dictionary defining configuration defaults
    WHEN get_rebaser_config is called
    AND an option doesn't exist in the config
    THEN the value from the dictionary is returned
    """
    defaults = {'git_name': 'TEST', 'remote_name': 'Wrong_name'}
    config = get_rebaser_config(defaults)

    assert config.git_name == defaults['git_name']


def test_get_rebaser_config_defaults_dont_override_ini_values(mock_config):
    """
    GIVEN a dictionary defining configuration defaults
    WHEN get_rebaser_config is called
    AND an option exists both in the ini config and the defaults dictionary
    THEN the value from the ini config is returned
    """
    defaults = {'git_name': 'TEST', 'remote_name': 'Wrong_name'}
    config = get_rebaser_config(defaults)

    assert config.remote_name == "test_remote_name"


def test_main_function(mock_env, mock_config, monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WHEN main() is called
    THEN GitRepo.rebase_to_hash is called with the correct parameters
    AND GitRepo.git.push is called
    """
    branch_name = 'test_branch'
    commit_to_rebase_to = '123456a'
    repo = MagicMock()

    with monkeypatch.context() as m:
        m.setattr(patch_rebaser.patch_rebaser, 'GitRepo',
                  Mock(return_value=repo))
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_repo', Mock())
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_branch',
                  Mock(return_value=branch_name))
        main()

    repo.branch.rebase_to_hash.assert_called_once_with(
        branch_name, commit_to_rebase_to)
    repo.git.push.assert_called()


def test_packages_to_process_skips_packages_not_in_the_list(
        mock_env, mock_config_with_pkgs_to_process, monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WITH packages_to_process set to a list of package names
    WHEN main() is called
    AND the package name given by DLRN is not in packages_to_process
    THEN the Rebaser is not called and the script ends early
    """
    mock_gitrepo = Mock()

    with monkeypatch.context() as m:
        m.setattr(patch_rebaser.patch_rebaser, 'GitRepo', mock_gitrepo)
        main()

    mock_gitrepo.assert_not_called()
