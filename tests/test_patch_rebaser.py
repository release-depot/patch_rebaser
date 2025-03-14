#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time

from git_wrapper import exceptions
from mock import MagicMock, Mock
import mock
import pytest

import patch_rebaser
from patch_rebaser.patch_rebaser import (
    create_patches_branch,
    find_patches_branch,
    get_rebaser_config,
    get_release_from_branch_name,
    main,
    parse_distro_info_path,
    parse_gerrit_remote_url,
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


def test_update_remote_patches_branch_no_changes_but_missing_commit(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN update_remote_patches_branch is called
    AND cherry_on_head_only returns false (indicating the local and remote
        branches have no differences)
    AND branch.remote_contains returns false (indicating the remote is missing
        an upstream commit)
    THEN git.push is called
    """
    mock_repo.branch.cherry_on_head_only.return_value = False
    mock_repo.branch.remote_contains.return_value = False

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)
    rebaser.update_remote_patches_branch()

    assert mock_repo.git.push.called is True


def test_update_remote_patches_branch_no_changes_and_commit_present(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN update_remote_patches_branch is called
    AND cherry_on_head_only returns false (indicating the local and remote
        branches have no differences)
    AND branch.remote_contains returns true
    THEN git.push is not called
    """
    mock_repo.branch.cherry_on_head_only.return_value = False
    mock_repo.branch.remote_contains.return_value = True

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)
    rebaser.update_remote_patches_branch()

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
                      "2019", dev_mode=True, release='2.1')
    rebaser.update_remote_patches_branch()

    # Tag not deleted, and pushed with -n for dry-run
    assert mock_repo.tag.delete.called is False
    assert mock_repo.git.push.called is True

    expected = [(("-n", "my_remote", "private-rebaser-2.1-2019-previous"),),
                (("-nf", "--follow-tags", "my_remote", "my_branch"),)]
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

    expected = [(("my_remote", "private-rebaser-unknown-2019-previous"),),
                (("-f", "--follow-tags", "my_remote", "my_branch"),)]
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
                      "000", dev_mode=True, release='15.0')

    mock_repo.commit.same.return_value = True
    rebaser.rebase_and_update_remote()

    assert mock_repo.tag.create.call_count == 1
    assert mock_repo.remote.fetch.call_count == 2

    expected = [(("-n", "my_remote", "private-rebaser-15.0-000-previous"),),
                (("-nf", "--follow-tags", "my_remote", "my_branch"),)]
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
    AND the git tag pushed contains the version from the branch name
    """
    branch_name = 'test-16.1-patches'
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

    # Check version in tag
    assert repo.git.push.mock_calls[0].args[2].startswith(
        'private-rebaser-16.1-') is True


def test_main_function_update_remote_url(mock_env, mock_config, monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WHEN main() is called
    AND remote url has changed
    THEN the remote.remove method is called
    """
    repo = MagicMock()
    monkeypatch.setattr(repo.remote, 'names_url_dict',
                        lambda: {"test_remote_name":
                                 "http://origin_remote.com"})

    with monkeypatch.context() as m:
        m.setattr(patch_rebaser.patch_rebaser, 'GitRepo',
                  Mock(return_value=repo))
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_repo',
                  Mock(return_value="http://test_repo.com"))
        main()
    repo.remote.remove.assert_called_once()


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


def test_rebase_exception_gitreview(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN perform_rebase asserts with RebaseException
    THEN Rebaser calls the try_automated_rebase_fix method
    """
    mock_repo.branch.rebase_to_hash.side_effect = [
        exceptions.RebaseException('.gitreview failed to rebase'),
        True]
    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)

    rebaser.try_automated_rebase_fix = Mock()
    rebaser.try_automated_rebase_fix.side_effect = [True]
    rebaser.perform_rebase()
    rebaser.try_automated_rebase_fix.assert_called()


@mock.patch('patch_rebaser.patch_rebaser._rebuild_gitreview')
def test_try_automated_rebase_fix(reb_mock, mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN perform_rebase asserts with RebaseException
    AND the exception contains .gitreview in the exception message
    AND Rebaser calls the try_automated_rebase_fix method
    THEN try_automated_rebase_fix detects .gitreview in the exception message
    AND calls git.rebase('--skip') and _rebuild_gitreview
    """

    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)

    exception = exceptions.RebaseException('.gitreview failed to rebase')
    output = rebaser.try_automated_rebase_fix(exception)

    mock_repo.git.rebase.assert_called_with('--skip')
    reb_mock.assert_called()
    assert output is True


def test_rebase_exception_not_gitreview(mock_repo):
    """
    GIVEN Rebaser initialized correctly
    WHEN perform_rebase asserts with RebaseException
    AND the exception message does not contain .gitreview
    THEN Rebaser calls the repo.branch.abort_rebase method
    """
    mock_repo.branch.rebase_to_hash.side_effect = [
        exceptions.RebaseException('Whatever other exception'),
        True]
    rebaser = Rebaser(mock_repo, "my_branch", "my_commit", "my_remote",
                      "my_tstamp", dev_mode=True)

    rebaser.repo.branch.abort_rebase = Mock()
    with pytest.raises(exceptions.RebaseException):
        rebaser.perform_rebase()
    rebaser.repo.branch.abort_rebase.assert_called()


def test_parse_gerrit_remote_url_ssh():
    """
    GIVEN a url containing protocol, host, port and project
    WHEN calling parse_gerrit_remote_url with the url
    THEN We get the expected values for host, port and project
    """
    host, port, project = parse_gerrit_remote_url(
        'ssh://code.example.com:22/kolla')

    assert host == 'code.example.com'
    assert port == '22'
    assert project == 'kolla'


def test_parse_gerrit_remote_url_https_noport():
    """
    GIVEN a url containing protocol, host, project but no port
    WHEN calling parse_gerrit_remote_url with the url
    THEN We get the expected values for host and project
    AND the expected default value for port (29418)
    """
    host, port, project = parse_gerrit_remote_url(
        'https://user@code.example.com/base/name')

    assert host == 'user@code.example.com'
    assert port == '29418'
    assert project == 'base/name'


def test_rebaser_missing_patches_branch_no_create(mock_env, mock_config,
                                                  monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WHEN main() is called
    AND the -patches branch is missing
    AND create_patches_branch is set to false
    THEN create_patches_branch is not called
    """
    repo = MagicMock()

    with monkeypatch.context() as m:
        m.setattr(patch_rebaser.patch_rebaser, 'GitRepo',
                  Mock(return_value=repo))
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_repo', Mock())
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_branch',
                  Mock(return_value=None))
        patch_rebaser.patch_rebaser.create_patches_branch = MagicMock()
        main()

    assert patch_rebaser.patch_rebaser.create_patches_branch.called is False


def test_rebaser_missing_patches_branch_create(
        mock_env, mock_config_with_create_patches_branch, monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WHEN main() is called
    AND the -patches branch is missing
    AND create_patches_branch is set to true
    THEN create_patches_branch is called
    """
    repo = MagicMock()

    with monkeypatch.context() as m:
        m.setattr(patch_rebaser.patch_rebaser, 'GitRepo',
                  Mock(return_value=repo))
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_repo', Mock())
        m.setattr(patch_rebaser.patch_rebaser, 'get_patches_branch',
                  Mock(return_value=None))
        patch_rebaser.patch_rebaser.create_patches_branch = MagicMock()
        main()

    assert patch_rebaser.patch_rebaser.create_patches_branch.called is True


def test_create_branch_with_dev_mode(mock_repo, mock_env, monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WHEN create_patches_branch() is called
    AND dev_mode is set to True
    THEN _rebuild_gitreview is called
    AND git.push is called with -nf as parameter
    """

    patch_rebaser.patch_rebaser._rebuild_gitreview = MagicMock()
    create_patches_branch(mock_repo, '123456a', 'my_remote')

    assert patch_rebaser.patch_rebaser._rebuild_gitreview.called is True
    assert mock_repo.git.push.called is True

    expected = [(("-n", "my_remote", "test-patches"),)]
    assert mock_repo.git.push.call_args_list == expected


def test_create_branch_without_dev_mode(mock_repo, mock_env, monkeypatch):
    """
    GIVEN a valid patch_rebaser configuration and environment
    WHEN create_patches_branch() is called
    AND dev_mode is set to False
    THEN _rebuild_gitreview is called
    AND git.push is called with -f as parameter
    """

    patch_rebaser.patch_rebaser._rebuild_gitreview = MagicMock()
    create_patches_branch(mock_repo, '123456a', 'my_remote', dev_mode=False)

    assert patch_rebaser.patch_rebaser._rebuild_gitreview.called is True
    assert mock_repo.git.push.called is True

    expected = [(("my_remote", "test-patches"),)]
    assert mock_repo.git.push.call_args_list == expected


def test_get_release_from_branch_name():
    branches = {
        "rhos-16.1-trunk-patches": "16.1",
        "rhos-90-trunk-patches": "90",
        "rhos-10.0-patches": "10.0",
        "my_branch": "Unknown",
        "rhos-18.0-foo-trunk-patches": "18.0-foo",
        "rhos-13.0-octavia-patches": "13.0-octavia",
        "rhos-10.0": "Unknown"
    }

    for branch, release in branches.items():
        assert get_release_from_branch_name(branch) == release
