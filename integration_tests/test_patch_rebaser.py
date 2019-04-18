from mock import patch
import os
import time

from git_wrapper.repo import GitRepo

from patch_rebaser.patch_rebaser import Rebaser


def test_rebase(local_repo, patches_repo_root):
    """
    GIVEN a local repository initialized with origin and upstream remotes
    WHEN running Rebaser.rebase_and_update_remote
    THEN the local repo is rebased to contain both upstream and origin commits
    AND the origin remote is updated with same
    """
    patches_repo = GitRepo(patches_repo_root)
    commit_to_rebase_to = "61a18a2a"

    # confirm we are the same as the patches repo
    local_repo_head = local_repo.repo.head.object.hexsha
    assert patches_repo.repo.head.object.hexsha == local_repo_head

    # confirm we have incoming patches from upstream
    assert len(
        local_repo.branch.cherry_on_head_only("master", commit_to_rebase_to)
    ) == 2

    # confirm we have additional patches compared to upstream
    assert len(local_repo.branch.cherry_on_head_only(
        commit_to_rebase_to, "master")
    ) == 1

    # Rebase with dev_mode off
    rebaser = Rebaser(
        local_repo, "master", commit_to_rebase_to, "origin", "0000", False
    )
    rebaser.rebase_and_update_remote()

    # confirm no more incoming patches from upstream
    assert len(
        local_repo.branch.cherry_on_head_only("master", commit_to_rebase_to)
    ) == 0

    # confirm we still have our additional patch
    assert len(local_repo.branch.cherry_on_head_only(
        commit_to_rebase_to, "master")
    ) == 1

    # assert remote repo was updated as well
    local_repo_head = local_repo.repo.head.object.hexsha
    assert patches_repo.repo.head.object.hexsha == local_repo_head


def test_rebase_doesnt_push_in_dev_mode(local_repo, patches_repo_root):
    """
    GIVEN a local repository initialized with origin and upstream remotes
    WHEN running Rebaser.rebase_and_update_remote
    WITH dev_mode set to True
    THEN the local repo is rebased
    AND the origin remote is not updated with the rebase results
    """
    patches_repo = GitRepo(patches_repo_root)
    commit_to_rebase_to = "61a18a2a"

    # confirm we are the same as the patches repo
    orig_local_repo_head = local_repo.repo.head.object.hexsha
    assert patches_repo.repo.head.object.hexsha == orig_local_repo_head

    # Rebase with dev_mode on
    rebaser = Rebaser(
        local_repo, "master", commit_to_rebase_to, "origin", "0000", True
    )
    rebaser.rebase_and_update_remote()

    # assert local repo was updated
    assert local_repo.repo.head.object.hexsha != orig_local_repo_head

    # assert remote repo was not updated
    assert patches_repo.repo.head.object.hexsha == orig_local_repo_head


def test_rebase_retry_logic(
        local_repo, patches_repo_root, datadir, monkeypatch):
    """
    GIVEN a local repository initialized with origin and upstream remotes
    WHEN running Rebaser.rebase_and_update_remote
    AND the remote branch changes during the rebase
    THEN the rebase operation gets run again
    AND the local repo is rebased and contains both upstream commits and all
        commits from the remote branch, including the new change
    AND the remote branch is updated with the rebase result
    """
    commit_to_rebase_to = "61a18a2acd05b2f37bd75164b8ddfdb71011fe68"
    orig_head = local_repo.repo.head.commit.hexsha

    # Mock sleep to avoid unnecessary waiting
    monkeypatch.setattr(time, 'sleep', lambda s: None)

    # Mock rebaser perform_rebase function so we can create a change
    # during that window
    rebaser = Rebaser(
        local_repo, "master", commit_to_rebase_to, "origin", "0000", False
    )
    orig_perform_rebase = rebaser.perform_rebase

    def modified_perform_rebase():
        apply_inflight_patch()
        orig_perform_rebase()

    def apply_inflight_patch():
        tmp_repo_root = "/tmp/test_retry"
        if os.path.exists(tmp_repo_root):
            # We already applied the inflight patch
            return
        else:
            tmp_repo = GitRepo.clone(patches_repo_root, tmp_repo_root)
            tmp_repo.branch.apply_patch("master", (datadir / "inflight.patch"))
            tmp_repo.git.push("origin", "master")

    # Confirm we have one local-only patch
    assert len(local_repo.branch.cherry_on_head_only(
        commit_to_rebase_to, "master")
    ) == 1

    # Test rebase with one inflight patch
    with patch.object(Rebaser, 'perform_rebase') as patched_rebase:
        patched_rebase.side_effect = modified_perform_rebase
        rebaser.rebase_and_update_remote()

    assert patched_rebase.call_count == 2

    # Now we have two local-only patches
    assert len(local_repo.branch.cherry_on_head_only(
        commit_to_rebase_to, "master")
    ) == 2

    # Check we have both local-only patches + upstream commits
    log = local_repo.branch.log_diff(orig_head, "master", "$hash $summary")
    assert "INFLIGHT" in log[0]
    assert "LOCAL-ONLY" in log[1]
    assert commit_to_rebase_to in log[2]

    patches_repo = GitRepo(patches_repo_root)
    assert patches_repo.repo.head.commit.hexsha in log[0]
