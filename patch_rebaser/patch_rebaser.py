#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Main module."""

try:
    import configparser
except ImportError:  # Python 2
    import ConfigParser as configparser
from datetime import datetime
import logging
import os
import time

from distroinfo import info, query
from git_wrapper import exceptions as git_exceptions
from git_wrapper.repo import GitRepo

LOGGER = logging.getLogger("patch_rebaser")


def find_patches_branch(repo, remote, distgit_branch):
    """Guess patches branch name"""
    # Adapted from rdopkg guess.find_patches_branch
    parts = distgit_branch.split('-')
    while parts:
        if 'trunk' in distgit_branch:
            branch = '%s-trunk-patches' % '-'.join(parts)
        else:
            branch = '%s-patches' % '-'.join(parts)
        LOGGER.debug("Checking if branch %s exists...", branch)
        if repo.branch.exists(branch, remote):
            return branch
        parts.pop()
    return None


def get_downstream_distgit_branch(dlrn_projects_ini):
    """Get downstream distgit branch info from DLRN projects.ini"""
    config = configparser.ConfigParser()
    config.read(dlrn_projects_ini)
    return config.get('downstream_driver', 'downstream_distro_branch')


def get_patches_branch(repo, remote, dlrn_projects_ini):
    """Get the patches branch name"""
    # Get downstream distgit branch from DLRN config
    distgit_branch = get_downstream_distgit_branch(dlrn_projects_ini)

    # Guess at patches branch based on the distgit branch name
    return find_patches_branch(repo, remote, distgit_branch)


def parse_distro_info_path(path):
    """Break distro_info path into repo + file"""
    path = path.strip().rsplit("/", 1)
    info_repo = path[0]
    info_file = path[1]
    remote = False

    if info_repo.startswith("http"):
        remote = True

    return info_file, info_repo, remote


def get_distro_info(distroinfo_repo):
    """Set up distro_info based on path"""
    info_file, info_repo, remote = parse_distro_info_path(distroinfo_repo)

    if remote:
        di = info.DistroInfo(info_file, remote_git_info=info_repo)
    else:
        di = info.DistroInfo(info_file, local_info=info_repo)

    return di.get_info()


def get_patches_repo(distroinfo_repo, pkg_name, key):
    """Get URL of repo with the patches branch"""
    distro_info = get_distro_info(distroinfo_repo)
    pkg = query.get_package(distro_info, pkg_name)
    repo = pkg.get(key)
    if not repo:
        LOGGER.warning("No %s repo listed for package %s", key, pkg_name)
    return repo


def get_rebaser_config():
    """Return a configparser object for patch_rebaser config"""
    # Get the config file location based on path of currently running script
    config_file = os.path.realpath(
        "{0}/{1}".format(
            os.path.dirname(os.path.realpath(__file__)),
            "patch_rebaser.ini"
        )
    )
    if not os.path.exists(config_file):
        raise Exception(
            "Configuration file {0} not found.".format(config_file)
        )

    rebaser_config = configparser.ConfigParser()
    rebaser_config.read(config_file)
    return rebaser_config


def set_up_git_config(name, email):
    os.environ["GIT_AUTHOR_NAME"] = name
    os.environ["GIT_AUTHOR_EMAIL"] = email
    os.environ["GIT_COMMITTER_NAME"] = name
    os.environ["GIT_COMMITTER_EMAIL"] = email


class Rebaser(object):

    def __init__(self, repo, branch, commit, remote, timestamp,
                 dev_mode=True, max_retries=3):
        """Initialize the Rebaser

       :param git_wrapper.GitRepo repo: An initialized GitWrapper repo
       :param str branch: Branch name to rebase (same name on local and remote)
       :param str commit: Commit sha to rebase to
       :param str remote: Remote name to use as base and push rebase result to
       :param str timestamp: Timestamp used in tag to previous remote HEAD
       :param bool dev_mode: Whether to run the push commands as dry-run only
       :param int max_retries: How many retry attempts if remote changed during
                               rebase
        """
        self.repo = repo
        self.branch = branch
        self.commit = commit
        self.remote = remote
        self.timestamp = timestamp
        self.tag_name = "private-rebaser-{0}-previous".format(timestamp)
        self.dev_mode = dev_mode
        self.max_retries = max_retries

        self.remote_branch = "{0}/{1}".format(self.remote, self.branch)

    def rebase_and_update_remote(self):
        """Rebase the local branch to the specific commit & push the result."""
        self.repo.remote.fetch(self.remote)

        # Reset the local branch to the latest
        self.repo.branch.create(self.branch,
                                self.remote_branch,
                                reset_if_exists=True)

        # Tag the previous branch's HEAD, before rebase
        self.repo.tag.create(self.tag_name, self.remote_branch)

        # Rebase
        self.perform_rebase()

        # Check if any new changes have come in
        self.repo.remote.fetch(self.remote)

        if not self.repo.commit.same(self.tag_name, self.remote_branch):
            if self.max_retries > 0:
                LOGGER.info("Remote changed during rebase. Remaining "
                            "attempts: %s", self.max_retries)
                time.sleep(20)
                self.max_retries -= 1

                # We'll need to move the tag to the new HEAD
                self.repo.tag.delete(self.tag_name)
                self.rebase_and_update_remote()
            else:
                # The remote changed several times while we were trying
                # to push the rebase result back. We stop trying for
                # now but leave the rebase results as is, so that the
                # build is still as up-to-date as can be. The patches
                # branch will be temporarily out of date, but that will
                # be corrected during the next Rebaser run.
                LOGGER.warning(
                    "Remote changed multiple times during rebase, not pushing."
                    " The build will include the current rebase result."
                )
        else:
            # No new stuff, push it on
            self.update_remote_patches_branch()

    def perform_rebase(self):
        """Rebase the specific local branch to the specific commit."""
        try:
            LOGGER.info("Rebasing %s to %s", self.branch, self.commit)
            self.repo.branch.rebase_to_hash(self.branch, self.commit)
        except git_exceptions.RebaseException:
            LOGGER.info("Could not rebase. Cleaning up.")
            self.repo.branch.abort_rebase()
            raise

    def update_remote_patches_branch(self):
        """Force push local patches branch to the remote repository.

        Also push the tag of what was the previous head of that remote branch.
        If in dev mode, the pushes are done in dry-run mode (-n).
        """
        # Do we need to push? If there are no changes between the remote
        # and the local branch, just delete the local tag and move on.
        if not self.repo.branch.cherry_on_head_only(
                self.remote_branch, self.branch):
            self.repo.tag.delete(self.tag_name)
            return

        if self.dev_mode:
            LOGGER.warning("Dev mode: executing push commands in dry-run mode")
            self.repo.git.push("-n", self.remote, self.tag_name)
            self.repo.git.push("-nf", self.remote, self.branch)
        else:
            LOGGER.warning(
                "Force-pushing {branch} to {remote} ({timestamp})".format(
                    branch=self.branch,
                    remote=self.remote,
                    timestamp=self.timestamp
                )
            )
            self.repo.git.push(self.remote, self.tag_name)
            self.repo.git.push("-f", self.remote, self.branch)


def main():
    # These variables are set up by DLRN
    user = os.environ['DLRN_USER']
    local_repo = os.environ['DLRN_SOURCEDIR']
    commit = os.environ['DLRN_SOURCE_COMMIT']
    distroinfo_repo = os.environ['DLRN_DISTROINFO_REPO']
    pkg_name = os.environ['DLRN_PACKAGE_NAME']

    # The next variables come from patch_rebaser.ini
    rebaser_config = get_rebaser_config()
    dev_mode = rebaser_config.getboolean('DEFAULT', 'dev_mode')
    remote = rebaser_config.get('DEFAULT', 'remote_name')
    git_name = rebaser_config.get('DEFAULT', 'git_name')
    git_email = rebaser_config.get('DEFAULT', 'git_email')
    patches_repo_key = rebaser_config.get('distroinfo', 'patches_repo_key')
    pkg_to_process = rebaser_config.get('DEFAULT', 'packages_to_process')
    try:
        dlrn_projects_ini = rebaser_config.get('DEFAULT', 'dlrn_projects_ini')
    except configparser.NoOptionError:
        dlrn_projects_ini = (
            "/usr/local/share/dlrn/{0}/projects.ini".format(user))

    if pkg_to_process:
        if "," in pkg_to_process:
            pkg_to_process = pkg_to_process.split(",")
        else:
            pkg_to_process = [pkg_to_process]

        if pkg_name not in pkg_to_process:
            LOGGER.info(
                "Skipping %s, as package not in list of packages_to_process",
                pkg_name
            )
            return

    set_up_git_config(git_name, git_email)

    repo = GitRepo(local_repo)

    # Create a remote for the patches branch
    patches_repo = get_patches_repo(
        distroinfo_repo, pkg_name, patches_repo_key
    )
    if not patches_repo:
        return

    if remote not in repo.remote.names():
        if not repo.remote.add(remote, patches_repo):
            raise Exception(
                "Could not add remote {0} ({1})".format(remote, patches_repo)
            )
    repo.remote.fetch_all()

    # Create local patches branch
    branch_name = get_patches_branch(repo, remote, dlrn_projects_ini)

    # Not every project has a -patches branch for every release
    if not branch_name:
        # TODO: (future) Create and set up patches branch
        return

    # Timestamp that will be used to tag the previous branch tip
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Perform rebase & force push result
    rebaser = Rebaser(repo, branch_name, commit, remote, timestamp, dev_mode)
    rebaser.rebase_and_update_remote()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        LOGGER.error(e)
        raise
