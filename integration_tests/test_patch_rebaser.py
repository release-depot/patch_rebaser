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
