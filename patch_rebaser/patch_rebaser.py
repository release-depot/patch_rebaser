#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Main module."""

try:
    import configparser
except ImportError:  # Python 2
    import ConfigParser as configparser
from collections import namedtuple
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


def create_patches_branch(repo, commit, remote, dev_mode=True):
    """Create new patches branch from commit"""
    branch_name = os.environ.get('PATCHES_BRANCH', None)
    if not branch_name:
        LOGGER.error("No PATCHES_BRANCH env var found, cannot create branch")
        return None

    if not repo.branch.create(branch_name, commit):
        LOGGER.error("Failed to create -patches branch")
        return None

    # Switch to the newly created branch
    # FIXME(jpena): Maybe include this in git_wrapper?
    repo.git.checkout(branch_name)
    _rebuild_gitreview(repo, remote, branch_name)

    # Finally, push branch before returning its name
    if dev_mode:
        LOGGER.warning("Dev mode: executing push commands in dry-run mode")
        repo.git.push("-n", remote, branch_name)
    else:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        LOGGER.warning(
            "Pushing {branch} to {remote} ({timestamp})".format(
                branch=branch_name,
                remote=remote,
                timestamp=timestamp
            )
        )
        repo.git.push(remote, branch_name)

    return branch_name


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


def get_release_from_branch_name(branch_name):
    try:
        return branch_name.split('-')[1]
    except IndexError:
        return 'Unknown'


def parse_distro_info_path(path):
    """Break distro_info path into repo + file"""
    path = path.strip().rsplit("/", 1)
    info_repo = path[0]
    info_file = path[1]
    remote = False

    if info_repo.startswith("http"):
        remote = True

    return info_file, info_repo, remote


def parse_gerrit_remote_url(url):
    """Break Gerrit remote url into host, port and project"""
    # We are expecting a remote URL in the format
    # protocol://host:port/project
    split_url = url.split('/')
    project = '/'.join(split_url[3:])   # The project part can contain slashes
    host_port = split_url[2].split(':')
    host = host_port[0]
    if len(host_port) > 1:
        port = host_port[1]
    else:
        port = '29418'        # Default Gerrit port
    return host, port, project


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


def get_rebaser_configparser(defaults=None):
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

    parser = configparser.ConfigParser(defaults)
    parser.read(config_file)
    return parser


def get_rebaser_config(defaults=None):
    """Return a tuple with the configuration information.

    If the configuration is missing an option, the value from the
    defaults dictionary is used. If the defaults doesn't contain the
    value either, a configparser.NoOptionError exception is raised.

       :param dict defaults: Default values for config values

    """
    default_options = ['dev_mode', 'remote_name', 'git_name', 'git_email',
                       'packages_to_process', 'dlrn_projects_ini',
                       'create_patches_branch']
    distroinfo_options = ['patches_repo_key']

    RebaserConfig = namedtuple('RebaserConfig',
                               default_options + distroinfo_options)

    parser = get_rebaser_configparser(defaults)

    options = {}
    for opt in default_options:
        if opt == 'dev_mode' or opt == 'create_patches_branch':
            options[opt] = parser.getboolean('DEFAULT', opt)
        elif opt == 'packages_to_process':
            pkgs = parser.get('DEFAULT', opt)
            if pkgs:
                pkgs = pkgs.split(",") if "," in pkgs else [pkgs]
            options[opt] = pkgs
        else:
            options[opt] = parser.get('DEFAULT', opt)

    if not parser.has_section('distroinfo'):
        parser.add_section('distroinfo')
    options['patches_repo_key'] = parser.get('distroinfo', 'patches_repo_key')

    return RebaserConfig(**options)


def set_up_git_config(name, email):
    """Set up environment variables for git author and committer info.

    This is a pre-requisite for performing a git rebase operation.
    """
    os.environ["GIT_AUTHOR_NAME"] = name
    os.environ["GIT_AUTHOR_EMAIL"] = email
    os.environ["GIT_COMMITTER_NAME"] = name
    os.environ["GIT_COMMITTER_EMAIL"] = email


def generate_gitreview(path, project, host, port, branch, remote):
    """Write a new .gitreview file to disk.

        :param str path: Directory where the file will be written
        :param str project: Name of the project
        :param str host: Gerrit host
        :param str port: Port for Gerrit host
        :param str branch: Git branch to use as defaultbranch
        :param str remote: Git remote to use as defaultremote
    """
    with open(os.path.join(path, '.gitreview'), 'w') as fp:
        fp.write("[gerrit]\n")
        fp.write("host=%s\n" % host)
        fp.write("port=%s\n" % port)
        fp.write("project=%s.git\n" % project)
        fp.write("defaultbranch=%s\n" % branch)
        fp.write("defaultremote=%s\n" % remote)
        fp.write("defaultrebase=1\n")


def _rebuild_gitreview(repo, remote, branch):
    dlrn = get_dlrn_variables()
    url = repo.repo.remote(remote).url
    if isinstance(url, list):
        url = url[0]
    host, port, project = parse_gerrit_remote_url(url)
    generate_gitreview(dlrn.local_repo, project, host, port, branch,
                       remote)
    # Now push the change
    repo.commit.commit('RHOS:  use internal gerrit - DROP-IN-RPM\n\n'
                       'Change-Id: I400187d0e03127743aad09d859988991'
                       'e965ff7e')


class Rebaser(object):

    def __init__(self, repo, branch, commit, remote, timestamp,
                 dev_mode=True, max_retries=3, release='unknown'):
        """Initialize the Rebaser

       :param git_wrapper.GitRepo repo: An initialized GitWrapper repo
       :param str branch: Branch name to rebase (same name on local and remote)
       :param str commit: Commit sha to rebase to
       :param str remote: Remote name to use as base and push rebase result to
       :param str timestamp: Timestamp used in tag to previous remote HEAD
       :param bool dev_mode: Whether to run the push commands as dry-run only
       :param int max_retries: How many retry attempts if remote changed during
                               rebase
       :param str release: Used in the tag name, informational only
        """
        self.repo = repo
        self.branch = branch
        self.commit = commit
        self.remote = remote
        self.timestamp = timestamp
        self.tag_name = (
            "private-rebaser-{release}-{timestamp}-previous".format(
                release=release, timestamp=timestamp)
        )
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
        rebase_done = False
        while not rebase_done:
            try:
                LOGGER.info("Rebasing %s to %s", self.branch, self.commit)
                self.repo.branch.rebase_to_hash(self.branch, self.commit)
                rebase_done = True
            except git_exceptions.RebaseException as e:
                if not self.try_automated_rebase_fix(e):
                    LOGGER.info("Could not rebase. Cleaning up.")
                    self.repo.branch.abort_rebase()
                    raise

    def try_automated_rebase_fix(self, exception):
        """Try to automatically fix a failed rebase.

        There will be a number of rebase failures we can try to fix in an
        automated way. Initially, failures related to the .gitreview file
        will be attempted.
        """
        if '.gitreview' in str(exception):
            LOGGER.warning("A patch including the .gitreview file failed "
                           "to rebase, skipping it.")
            try:
                self.repo.git.rebase('--skip')
                _rebuild_gitreview(self.repo, self.remote, self.branch)
                return True
            except Exception as e:
                LOGGER.error("Failed to fix rebase error: %s" % e)
                return False
        return False

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


def get_dlrn_variables():
    """Return environment variables that are set by DLRN"""
    DLRNConfig = namedtuple(
        'DLRNConfig',
        ['user', 'local_repo', 'commit', 'distroinfo_repo', 'pkg_name']
    )

    return DLRNConfig(
        os.environ['DLRN_USER'],
        os.environ['DLRN_SOURCEDIR'],
        os.environ['DLRN_SOURCE_COMMIT'],
        os.environ['DLRN_DISTROINFO_REPO'],
        os.environ['DLRN_PACKAGE_NAME']
    )


def main():
    dlrn = get_dlrn_variables()

    # Default values for options in patch_rebaser.ini
    defaults = {
        'remote_name': 'remote_name',
        'git_name': 'Your Name',
        'git_email': 'you@example.com',
        'packages_to_process': '',
        'dlrn_projects_ini': (
            '/usr/local/share/dlrn/{0}/projects.ini'.format(dlrn.user)),
        'dev_mode': 'true',
        'patches_repo_key': 'patches',
        'create_patches_branch': 'false'
    }

    config = get_rebaser_config(defaults)

    if config.packages_to_process and \
       dlrn.pkg_name not in config.packages_to_process:
        LOGGER.info(
            "Skipping %s, as package not in list of packages_to_process",
            dlrn.pkg_name
        )
        return

    set_up_git_config(config.git_name, config.git_email)

    repo = GitRepo(dlrn.local_repo)

    # Create a remote for the patches branch
    patches_repo = get_patches_repo(
        dlrn.distroinfo_repo, dlrn.pkg_name, config.patches_repo_key
    )
    if not patches_repo:
        return

    if config.remote_name not in repo.remote.names():
        if not repo.remote.add(config.remote_name, patches_repo):
            raise Exception(
                "Could not add remote {0} ({1})".format(config.remote_name,
                                                        patches_repo)
            )
    repo.remote.fetch_all()

    # Create local patches branch
    branch_name = get_patches_branch(repo,
                                     config.remote_name,
                                     config.dlrn_projects_ini)

    # Not every project has a -patches branch for every release
    if not branch_name:
        if config.create_patches_branch:
            LOGGER.warning('Patches branch does not exist, creating it')
            branch_name = create_patches_branch(
                repo, dlrn.commit, config.remote_name,
                dev_mode=config.dev_mode)
            if not branch_name:
                raise Exception('Could not create -patches branch')
        else:
            LOGGER.warning('Patches branch does not exist, not creating it')

        # We do not need to rebase now, since the branch was
        # created on using the upstream commit as a HEAD
        return

    # Timestamp that will be used to tag the previous branch tip
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Release will also be used in the tag name
    release = get_release_from_branch_name(branch_name)

    # Perform rebase & force push result
    rebaser = Rebaser(repo,
                      branch_name,
                      dlrn.commit,
                      config.remote_name,
                      timestamp,
                      config.dev_mode,
                      release=release)

    rebaser.rebase_and_update_remote()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        LOGGER.error(e)
        raise
