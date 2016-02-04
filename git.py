#!/usr/bin/python

"""
Utility classes for working with Git.
"""

import re
import os
import os.path
import subprocess
import tempfile

def flip(t):
    a, b = t
    return b, a

class GitRepository(object):
    # Currently hard-coded, but the idea is to have enough flexibility to make
    # the class work with other remotes
    remote = 'origin'

    def __init__(self, root):
        self.root = root
        self.rev_cache = {}

    def cmd(self, *args, **kwargs):
        """Invoke a shell command in the specified repository."""

        cmd = list(args)
        return subprocess.check_output(cmd, stderr = subprocess.STDOUT, cwd = self.root, **kwargs).strip()

    def git(self, *args, **kwargs):
        """Invoke git(1) for the specified repository."""

        args_flattened = tuple(arg.hash if isinstance(arg, GitCommit) else arg for arg in args)
        return self.cmd(*(('git',) + args_flattened), **kwargs)

    def get_refs(self, remote=False):
        output = self.git('ls-remote', self.remote) if remote else self.git('show-ref')
        lines = output.splitlines()
        lines = map(str.strip, lines)
        return dict(flip(re.split(r"\s+", line, 2)) for line in lines if line)

    def has_branch(self, name, local_only = False):
        local_ref = 'refs/heads/%s' % name
        remote_ref = 'refs/remotes/%s/%s' % (self.remote, name)

        refs = self.get_refs()
        return local_ref in refs or (not local_only and remote_ref in refs)

    def get_rev(self, name):
        if name not in self.rev_cache:
            self.rev_cache[name] = GitCommit(self, name)

        return self.rev_cache[name]

    def read_branch_head(self, name):
        return self.get_rev('refs/heads/%s^{}' % name)

    def read_tag(self, name):
        return self.get_rev('refs/tags/%s^{}' % name)

    def clean(self):
        self.git('clean', '-xfd')
        self.git('reset', '--hard')

    def remote_checkout(self, branch):
        self.clean()
        self.git('checkout', '-B', branch, '%s/%s' % (self.remote, branch))

    def get_common_ancestor(self, rev1, rev2):
        return GitCommit(self, self.git('merge-base', rev1, rev2))

    def is_ancestor(self, rev_older, rev_newer):
        """Checks if the rev_older is an ancestor of rev_newer. Returns true
        in case if two revisions are equal."""

        try:
            self.git('merge-base', '--is-ancestor', rev_older, rev_newer)
            return True
        except subprocess.CalledProcessError as err:
            if err.returncode == 1:
                return False
            else:
                raise

    def get_object_type(self, obj):
        return self.git('cat-file', '-t', obj).strip()

    def import_tarball(self, tarfile, rev):
        if isinstance(rev, GitCommit):
            rev = rev.hash

        self.cmd('pristine-tar', 'commit', tarfile, rev)

    def export_tarball(self, tarfile):
        self.cmd('pristine-tar', 'checkout', tarfile)

    def list_tarballs(self):
        return [s.strip() for s in self.cmd('pristine-tar', 'list').split("\n") if s.strip()]

    def get_tarball_tree(self, tarfile):
        try:
            return self.git('cat-file', 'blob', "refs/heads/pristine-tar:%s.id" % tarfile)
        except subprocess.CalledProcessError as err:
            return None

    def push(self, ref):
        self.git('push', self.remote, ref)

class GitCommit(object):
    def __init__(self, repo, name):
        self.repo = repo
        self.hash = repo.git('rev-parse', name)

        self.desc = repo.git('cat-file', 'commit', self.hash).strip()

        lines = self.desc.split("\n")
        seperator = lines.index('')
        fields = [line.split(' ', 1) for line in lines[0:seperator]]
        self.summary = "\n".join(lines[seperator+1:])

        self.tree, = (field[1] for field in fields if field[0] == 'tree')
        self.parents = [field[1] for field in fields if field[0] == 'parent']

    def checkout(self):
        self.repo.clean()
        self.repo.git('checkout', self.hash)

    def read_file(self, path):
        pathspec = "%s:%s" % (self.hash, path)
        return self.repo.git('cat-file', 'blob', pathspec)

    def file_exists(self, path):
        try:
            self.read_file(path)
        except subprocess.CalledProcessError:
            return False

        return True

    def extract_tree(self, path):
        indexfile = tempfile.mktemp()

        env = os.environ.copy()
        env['GIT_WORK_TREE'] = path
        env['GIT_INDEX_FILE'] = indexfile

        self.repo.git('read-tree', self.tree, env=env)
        self.repo.git('checkout-index', '-a', env=env)

        os.unlink(indexfile)

    def annotated_tag(self, name, message, key=None):
        if key:
            self.repo.git('tag', '-s', name, self.hash, '-m', message, '-u', key)
        else:
            self.repo.git('tag', '-a', name, self.hash, '-m', message)

    def __eq__(self, rev2):
        return self.hash == rev2.hash

    def __ne__(self, rev2):
        return self.hash != rev2.hash

    def __le__(self, rev2):
        return self.repo.is_ancestor(self.hash, rev2.hash)

    def __ge__(self, rev2):
        return self.repo.is_ancestor(rev2.hash, self.hash)

    def __lt__(self, rev2):
        return self <= rev2 and not self == rev2

    def __gt__(self, rev2):
        return self >= rev2 and not self == rev2

    def __and__(self, rev2):
        """Find common ancestor of two revisions."""

        return self.repo.get_common_ancestor(self, rev2)

    def __str__(self):
        return self.hash

    def __repr__(self):
        return "<commit '%s' in repository '%s'>" % (self.hash, self.repo.root)
