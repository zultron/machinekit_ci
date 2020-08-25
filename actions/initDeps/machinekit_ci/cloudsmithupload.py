#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Upload packages to Cloudsmith
"""

import argparse
import sh
import os
import sys
import re
import json

import machinekit_ci.script_helpers as helpers

unset = object()

class CloudsmithUploader(helpers.DistroSettings):
    def __init__(self: object, path, package_directory):
        super(CloudsmithUploader, self).__init__(path)
        self.package_directory = helpers.NormalizeSubdir(package_directory)()

    _cache_dict = {}
    def _cache_get(self: object, key, default=unset):
        if default is unset:
            return self._cache_dict[key] # Raises KeyError if absent
        else:
            return self._cache_dict.get(key, default)

    def _cache_set(self: object, key, value):
        self._cache_dict[key] = value
        return value

    @property
    def repo_slug(self):
        return self.distro_settings.get('cloudsmith_repo_slug', self.package)

    cloudsmith_whoami_regex = re.compile(r'slug: *([^,]*),', flags=re.MULTILINE)
    @property
    def namespace(self: object):
        if self._cache_get('namespace', None) is None:
            whoami_text = sh.cloudsmith.whoami(_tty_out=False)
            whoami_match = self.cloudsmith_whoami_regex.search(str(whoami_text))
            namespace = whoami_match.group(1)
            sys.stderr.write('Discovered Cloudsmith namespace {}\n'.format(namespace))
            return self._cache_set('namespace', namespace)
        return self._cache_get('namespace')

    @property
    def repo(self: object):
        if self._cache_get('repo', None) is None:
            repos_json = sh.cloudsmith.list.repos('--output-format=json', _tty_out=False)
            repos = json.loads(str(repos_json))
            for repo in repos['data']:
                if repo['namespace'] == self.namespace and repo['slug'] == self.repo_slug:
                    break
            else:
                raise ValueError("No Cloudsmith repo found in {} namespace with {} slug".format(
                    self.namespace, self.repo_slug))
            sys.stderr.write("Found Cloudsmith repo, namespace {}, slug {}\n".format(
                    self.namespace, self.repo_slug))
            return self._cache_set('repo', repo)
        return self._cache.get('repo')

    package_regex = re.compile(r'^[^_]+_(.*)_([^.]*)\.d?deb$')
    def walk_package_directory(self: object):
        # Walk package_directory, yielding (subdir, fname) on matches
        for subdir, _, files in os.walk(self.package_directory):
            for fname in files:
                match = self.package_regex.match(fname)
                if match:
                    yield((subdir, fname))

    ordr_regex = re.compile(r'^.+-([^-]+)-([^-]+)-([^-]+)-[^-]+-[^-]+$')
    def ordr(self: object, subdir):
        topdir = subdir.split('/')[-1]
        match = self.ordr_regex.match(topdir)
        distro = match.group(1)
        release = match.group(2)
        return '{}/{}/{}/{}'.format(self.namespace, self.repo_slug, distro, release)

    def upload_packages(self: object, dry_run=False):
        for dirname, fname in self.walk_package_directory():
            ordr = self.ordr(dirname)
            sys.stderr.write("Uploading package {} {}\n".format(ordr, fname))
            args = ['--republish', ordr, fname]
            if dry_run:
                sys.stderr.write("cloudsmith push deb {} {} {}\n".format(*args))
            else:
                sh.cloudsmith.push.deb(*args,
                                       _out=sys.stdout.buffer,
                                       _err=sys.stderr.buffer,
                                       _cwd=dirname)

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Upload packages to Cloudsmith")

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=helpers.PathExistsAction,
                            dest="path",
                            default=os.getcwd(),
                            help="Path to root of git repository")
        parser.add_argument("--package-directory",
                            default=os.getcwd(),
                            help="Directory containing packages")
        parser.add_argument("--dry-run",
                            action="store_true",
                            help="Show what would be done, but don't do anything")

        args = parser.parse_args()

        try:
            cloudsmith_uploader = cls(
                args.path, args.package_directory)
            cloudsmith_uploader.upload_packages(dry_run=args.dry_run)
        except ValueError as e:
            sys.stderr.write(str(e) + '\n')
            sys.exit(1)
