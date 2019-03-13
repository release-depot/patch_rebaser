#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Main module."""

try:
    import configparser
except ImportError:  # Python 2
    import ConfigParser as configparser
import logging
import os

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


def main():
    # These variables are set up by DLRN
    user = os.environ['DLRN_USER']
    local_repo = os.environ['DLRN_SOURCEDIR']
    commit = os.environ['DLRN_SOURCE_COMMIT']
    distroinfo_repo = os.environ['DLRN_DISTROINFO_REPO']
    pkg_name = os.environ['DLRN_PACKAGE_NAME']

    # The next variables come from patch_rebaser.ini
    rebaser_config = get_rebaser_config()
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
    branch = get_patches_branch(repo, remote, dlrn_projects_ini)

    # Not every project has a -patches branch for every release
    if not branch:
        # TODO: (future) Create and set up patches branch
        return

    remote_branch = "{remote}/{branch}".format(remote=remote, branch=branch)
    repo.branch.create(branch, remote_branch, reset_if_exists=True)

    # Rebase
    try:
        LOGGER.info("Rebasing %s to %s", branch, commit)
        repo.branch.rebase_to_hash(branch, commit)
    except git_exceptions.RebaseException:
        LOGGER.info("Could not rebase. Cleaning up.")
        repo.branch.abort_rebase()
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        LOGGER.error(e)
        raise
