#!/usr/bin/python

import datetime
import re
import os
import os.path
import sys
import subprocess
import traceback

import git

config_repo_path = os.environ['XREF_CONFIG']
sources_path = os.environ['XREF_SOURCES']

#
# VCS-specific handling
#

class SourceRepositoryUpdater(object):
    def configure(self, path, config):
        self.path = path
        self.source = config

    def init_repo(self):
        raise NotImplementedError()

    def update_repo(self):
        raise NotImplementedError()

class GitRepositoryUpdater(SourceRepositoryUpdater):
    def init_repo(self):
        subprocess.check_call(['git', 'clone', self.source, self.path])

    def update_repo(self):
        repo = git.GitRepository(self.path)
        repo.git('remote', 'set-url', 'origin', self.source)
        repo.git('fetch', '--all')
        repo.remote_checkout('master')

vcs_updaters = {
    'git' : GitRepositoryUpdater,
}

#
# Actual update logic
#

def load_repositories(refresh=True):
    """
    Refreshes and loads new repository map.
    """

    if refresh:
        config_repo = git.GitRepository(config_repo_path)
        config_repo.git('fetch', '--all')
        config_repo.remote_checkout('master')

    config_file_path = os.path.join(config_repo_path, 'sourcemap')
    config_file = open(config_file_path, 'r')
    repo_map = {}
    for line in config_file:
        line = line.strip()
        line = re.sub("#.*", "", line)
        line = line.strip()
        if not line:
            continue

        name, vcs, config = line.split(' ', 2)
        path = os.path.join(sources_path, name)

        repo_map[name] = vcs_updaters[vcs]()
        repo_map[name].configure(path, config)

    return repo_map

def log_timestamp(comment):
    timestamp = datetime.datetime.now().isoformat()
    print "%s, %s" % (comment, timestamp)

def do_updates():
    print "Loading repository configuration..."
    repo_map = load_repositories()
    print "Successfully loaded %i repositories!" % len(repo_map)
    print

    # Update the checkouts
    log_timestamp("Repository update")
    for repo_name, updater in repo_map.iteritems():
        repo_path = updater.path
        if os.path.isdir(repo_path):
            try:
                print "Updating %s..." % repo_name
                sys.stdout.flush()
                updater.update_repo()
                print "Update successful!"
            except:
                print "Update failed :("
                traceback.print_exc()
            sys.stdout.flush()
        else:
            try:
                print "Initializing %s..." % repo_name
                sys.stdout.flush()
                updater.init_repo()
                print "Checkout successful!"
            except:
                print "Checkout failed :("
                traceback.print_exc()
            sys.stdout.flush()
        print

    log_timestamp("Index update")

    try:
        print "Running OpenGrok index..."
        sys.stdout.flush()
        subprocess.check_call(["/usr/opengrok/OpenGrok", "index"])
        print "Indexing was successful!"
    except:
        print "Indexing failed :("
        traceback.print_exc()
    sys.stdout.flush()

    print
    log_timestamp("Finished")

if __name__ == '__main__':
    do_updates()
