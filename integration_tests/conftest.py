import shutil

from git_wrapper.repo import GitRepo
import pytest


UPSTREAM_REPO_ROOT = "/repos/upstream_repo"  # Upstream equivalent
PATCHES_REPO_ROOT = "/repos/patches_repo"  # Behind upstream + extra commits
LOCAL_REPO_ROOT = "/repos/local_repo"  # Same as patches repo, used for rebase


@pytest.fixture(scope="function")
def local_repo(datadir):
    """A clone of the patches repo, with a remote to the 'upstream' repo"""
    set_up_patches_repo(datadir)

    local_repo = GitRepo.clone(PATCHES_REPO_ROOT, LOCAL_REPO_ROOT)
    local_repo.remote.add("upstream", UPSTREAM_REPO_ROOT)

    yield local_repo

    # Clean up before the next run
    shutil.rmtree(LOCAL_REPO_ROOT, ignore_errors=True)
    shutil.rmtree(PATCHES_REPO_ROOT, ignore_errors=True)


@pytest.fixture(scope="function")
def patches_repo_root():
    yield PATCHES_REPO_ROOT


def set_up_patches_repo(datadir):
    """Set up an older copy of the upstream repo, and add an extra commit"""
    tmp_repo = "/tmp/patches_repo"

    upstream_repo = GitRepo(UPSTREAM_REPO_ROOT)
    tmp_patches_repo = GitRepo.clone(UPSTREAM_REPO_ROOT, tmp_repo)

    upstream_head = upstream_repo.repo.head.object.hexsha
    assert tmp_patches_repo.repo.head.object.hexsha == upstream_head

    # Set the local repo back a few commits (so there is something to
    # rebase from upstream)
    tmp_patches_repo.branch.hard_reset_to_ref("master", "b96f74b3")
    assert tmp_patches_repo.repo.head.object.hexsha != upstream_head

    # And also add a local-only patch
    patch_path = (datadir / "local-only.patch")
    tmp_patches_repo.branch.apply_patch("master", patch_path)

    # Finally, now that the repo preparations are done, get a bare clone ready
    GitRepo.clone(tmp_repo, PATCHES_REPO_ROOT, bare=True)

    shutil.rmtree(tmp_repo, ignore_errors=True)
