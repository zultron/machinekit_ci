#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#####################################################################
# Description:  buildcontainerimage.py
#
#               This file, 'buildcontainerimage.py', implements
#               functions used for assembling Docker images for
#               building native binaries
#
#               It requires the `sh` Python module
#
# Copyright (C) 2020    Jakub Fišer  <jakub DOT fiser AT eryaf DOT com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
######################################################################

"""
Script for building Docker container images for a CI build system
"""

# Debian 9 Stretch, Ubuntu 18.04 Bionic and (probably) other older distributions
# need in environment LANG=C.UTF-8 (or other similar specification of encoding)
# to properly function

__license__ = "LGPL 2.1"

import os
import argparse
import sh
import sys
import datetime
import machinekit_ci.script_helpers as helpers
from docker_registry_client import BaseClient
import requests
import shutil
import tempfile
import pkg_resources


class BuildContainerImage(helpers.DistroSettings):
    def __init__(self: object, path, dockerfile=None, entrypoint=None):
        super(BuildContainerImage, self).__init__(path)
        self._dockerfile_path = dockerfile
        self._entrypoint_path = entrypoint
        self.get_git_data()

    @property
    def docker_registry_repo(self: object):
        return "{}/{}".format(self.docker_registry_namespace, self.image_name)

    def _docker_registry_client(self: object):
        return BaseClient(
            self.env('DOCKER_REGISTRY_URL'),
            username=self.env('DOCKER_REGISTRY_USER'),
            password=self.env('DOCKER_REGISTRY_PASSWORD'),
        )

    def get_cached_image_labels(self: object):
        client = self._docker_registry_client()
        try:
            manifest, digest = client.get_manifest_and_digest(
                self.docker_registry_repo, self.image_tag)
            config_digest = manifest.get('config').get('digest')
            config_blob = client.get_blob(
                self.docker_registry_repo, config_digest)
            return config_blob['content']['config']['Labels']
        except requests.exceptions.HTTPError as e:
            sys.stderr.write("No cached image: {}\n".format(e))
            return None

    def get_git_data(self: object) -> None:
        self.git_sha = sh.git("rev-parse",
                              "HEAD",
                              _tty_out=False,
                              _cwd=self.normalized_path).strip()
        self.author_name = sh.git("show",
                                  "-s",
                                  "--pretty=%an",
                                  "HEAD",
                                  _tty_out=False,
                                  _cwd=self.normalized_path).strip()
        self.author_email = sh.git("show",
                                   "-s",
                                   "--format=%ae",
                                   "HEAD",
                                   _tty_out=False,
                                   _cwd=self.normalized_path).strip()
        self.git_remote_url = sh.git("ls-remote",
                                     "--get-url",
                                     _tty_out=False,
                                     _cwd=self.normalized_path).strip()

    @property
    def dockerfile_path(self: object):
        if self._dockerfile_path is not None:
            return self._dockerfile_path
        return pkg_resources.resource_filename(__name__, 'Dockerfile')

    @property
    def entrypoint_path(self: object):
        if self._entrypoint_path is not None:
            return self._entrypoint_path
        return pkg_resources.resource_filename(__name__, 'entrypoint')

    def docker_context_cm(self: object):
        """Create a pristine Docker context from git archive of the .github/docker and
        debian directories, adding Dockerfile and entrypoint from GH Action
        directory, and yield this as a context manager
        """
        with tempfile.TemporaryDirectory(prefix='mk-ci-tmp-context-') as context_dir:
            sh.tar(
                sh.git.archive(
                    "--format=tar", "HEAD", "--", ".github/docker", self.debian_dir,
                    _err=sys.stderr.buffer,
                    _cwd=self.normalized_path),
                "xvf", "-",
                _err=sys.stderr.buffer,
                _cwd=context_dir)
            for src in (self.dockerfile_path, self.entrypoint_path):
                fname = os.path.basename(src)
                dest = os.path.join(context_dir, fname)
                print(repr(src), repr(dest))
                shutil.copyfile(src, dest)
                shutil.copymode(src, dest)
            yield context_dir

    def generate_image_hash(self):
        """Generate hash of Docker context

        - Recursively list all files
        - Get sha1sum of each file in list
        - Sort list (ensures consistency from run to run)
        - Get final sha1sum of list
        """
        for context_dir in self.docker_context_cm():
            sha1sum = sh.sha1sum(
                sh.xargs(
                    sh.sort(
                        sh.find(
                            '.', '-type', 'f', '-print0',
                            _err=sys.stderr.buffer,
                            _cwd=context_dir),
                        '-z',
                        # Locale differences can affect sort order
                        _env = {**os.environ, 'LC_ALL': 'C.UTF-8'},
                        _err=sys.stderr.buffer),

                    '-0', 'sha1sum',
                    _err=sys.stderr.buffer,
                    _cwd=context_dir),
                _err=sys.stderr.buffer).split()[0]
        return sha1sum

    def build_opt(self: object, args: list, name: str, value: str):
        args.append("--{}={}".format(name, value))

    def build_arg(self: object, args: list, name: str, value: str):
        self.build_opt(args, "build-arg", "{}={}".format(name, value))

    def build_label(self: object, args: list, name: str, value: str):
        self.build_opt(args, "label", "{}.{}={}".format(
            self.label_prefix, name, value))

    def list_directory(self: object, path: str, ls_opts=['-l'], to_stderr=False):
        sh_xargs_kwargs = dict(
            _out = sys.stderr.buffer if to_stderr else sys.stderr.buffer,
            _in = sys.stderr.buffer,
            _cwd = path,
        )
        sh.xargs(
            sh.find('.', '-type', 'f',
                    _cwd = path),
            'ls', *ls_opts, **sh_xargs_kwargs)

    def build_image(self: object, target=None, dry_run=False) -> None:
        if any(tested is None for tested in [self.armed_base_image,
                                             self.armed_architecture,
                                             self.armed_os_release,
                                             self.armed_vendor,
                                             self.armed_os_codename]
               ):
            raise ValueError("Not all values are prepared for build.")
        tag_suffix = ('-'+target) if target else ""
        image_name = self.image_registry_name_tag + tag_suffix
        image_hash = self.generate_image_hash()

        # `docker build` command and arguments
        docker_build = sh.docker.bake("build")

        args = list()
        # --build-arg
        self.build_arg(args, 'DEBIAN_DISTRO_BASE', self.armed_base_image)
        self.build_arg(args, 'HOST_ARCHITECTURE', self.armed_architecture)
        self.build_arg(args, 'DEBIAN_DIR', self.debian_dir)
        self.build_arg(args, 'ENTRYPOINT', 'entrypoint')

        if self.script_pre_cmd:
            self.build_arg(args, 'SCRIPT_PRE_CMD', self.script_pre_cmd)
        if self.script_post_cmd:
            self.build_arg(args, 'SCRIPT_POST_CMD', self.script_post_cmd)
        # --label
        self.build_label(args, 'maintainer_name', self.author_name)
        self.build_label(args, 'maintainer_email', self.author_email)
        self.build_label(args, 'project', self.project_name)
        self.build_label(args, 'os_vendor', self.armed_vendor.capitalize())
        self.build_label(args, 'os_codename', self.armed_os_codename)
        self.build_label(args, 'host_architecture', self.armed_architecture)
        self.build_label(args, 'build-date',
                         datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.build_label(args, 'vcs-ref', self.git_sha)
        self.build_label(args, 'vcs-url', self.git_remote_url)
        self.build_opt(args, 'label', '{}={}'.format(
            self.image_hash_label, image_hash))
        # - Other args
        self.build_opt(args, 'file', 'Dockerfile')
        self.build_opt(args, 'tag', image_name)
        self.build_opt(args, 'progress', 'plain')
        if target is not None:
            self.build_opt(args, 'target', target)

        # Set up Docker context
        for context_dir in self.docker_context_cm():
            # Build directory
            args.append(context_dir)

            # sh.docker.build args
            if sys.stdout.isatty():
                sh_kwargs = dict(_fg = True)
            else:
                sh_kwargs = dict(_out = sys.stdout.buffer, _in = sys.stderr.buffer)
            sh_kwargs.update(dict(_cwd=context_dir))

            # Show `docker build` command and list build context files
            sys.stderr.write("Building image, {} {} {}, hash {}; command:\n".format(
                self.armed_vendor, self.armed_os_codename, self.armed_architecture, image_hash))
            sys.stderr.write("    docker build \\\n   '{}'\n".format(
                "' \\\n   '".join(args)))
            sys.stderr.write("sh_kwargs: {}\n".format(sh_kwargs))
            sys.stderr.write('Docker context, {}\n'.format(context_dir))
            self.list_directory(context_dir, to_stderr=True)
            sys.stderr.flush
            sys.stdout.flush

            # Run `docker build` (or show what would run)
            if not dry_run:
                docker_build(*args, **sh_kwargs)

    def push_image(self: object, dry_run=False):
        print("Command:  docker push {}".format(self.image_registry_name_tag))
        if not dry_run:
            sh.docker.push(self.image_registry_name_tag,
                           _out=sys.stdout.buffer,
                           _err=sys.stderr.buffer,
            )

    def get_registry_image_hash(self: object):
        labels = self.get_cached_image_labels()
        if labels is None:
            return (None, "No cached image in registry")
        image_hash = labels.get(self.image_hash_label, None)
        if image_hash is None:
            return (None, "Cached image in registry has no label '{}'").format(
                self.image_hash_label)
        source_hash = self.generate_image_hash()
        if image_hash == source_hash:
            return (image_hash, "Found matching cached image, hash '{}'".format(
                self.image_hash_label))
        return (image_hash, "Found mismatched cached image, hash '{}'".format(
            self.image_hash_label))

    def list_registry_image_labels(self: object):
        labels = self.get_cached_image_labels()
        if labels is None:
            sys.stderr.write("No cached image in registry\n")
            return
        for label, value in labels.items():
            print("{} {}".format(label, value))

    def pull_image(self: object, dry_run=False) -> bool:
        image_hash, result_message = self.get_registry_image_hash()
        if image_hash is None:
            sys.stderr.write(result_message + "\n")
            return False
        source_hash = self.generate_image_hash()
        if image_hash != source_hash:
            sys.stderr.write("Local hash {} != registry image hash {}\n".format(
                source_hash, image_hash))
            sys.stderr.write("Not pulling from registry\n")
            return False

        sys.stderr.write("Pulling image, {} {} {}, hash {}; command:\n".format(
            self.armed_vendor, self.armed_os_codename, self.armed_architecture, image_hash))
        sys.stderr.write("    docker pull {}\n".format(self.image_registry_name_tag))
        if not dry_run:
            sh.docker.pull(self.image_registry_name_tag,
                           _out=sys.stdout.buffer,
                           _err=sys.stderr.buffer,
            )
        return True

    def show_hash(self:object):
        print(self.generate_image_hash())

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Build container images")

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=helpers.PathExistsAction,
                            dest="path",
                            help="Path to root of git repository")
        parser.add_argument("--build",
                            action="store_true",
                            help="Build Docker image")
        parser.add_argument("-t",
                            "--target",
                            action="store",
                            dest="target",
                            metavar=("TARGET"),
                            help="Dockerfile target to build")
        parser.add_argument("--dry-run",
                            action="store_true",
                            help="Show the 'docker build' command but don't actually run")
        parser.add_argument("--dockerfile",
                            help="Path to Dockerfile, default Dockerfile")
        parser.add_argument("--entrypoint",
                            help="Path to entrypoint script, default entrypoint")
        parser.add_argument("--push",
                            action="store_true",
                            help="Push Docker image")
        parser.add_argument("--list-registry",
                            action="store_true",
                            help="List registry image labels")
        parser.add_argument("--pull",
                            action="store_true",
                            help="Pull Docker image (only if matching local repo)")
        parser.add_argument("--show-hash",
                            action="store_true",
                            help="Show local source tree image hash (for debugging)")

        # Positional arguments
        parser.add_argument("version",
                            metavar="VERSION",
                            action="store",
                            help="Distribution version/codename for which the image will be build")
        parser.add_argument("architecture",
                            metavar="ARCHITECTURE",
                            action="store",
                            help="Architecture specifics for which the image will be build")

        args = parser.parse_args()

        try:
            buildcontainerimage = BuildContainerImage(
                args.path, dockerfile=args.dockerfile, entrypoint=args.entrypoint,
            )

            if not buildcontainerimage.set_os_arch_combination(
                    args.version, args.architecture):
                raise ValueError("Wanted combination of {0} {1} {2} is not possible to be build.".format(
                    args.version, args.architecture))

            if args.build:
                buildcontainerimage.build_image(
                    target=args.target, dry_run=args.dry_run,
                )
                if not args.dry_run:
                    print("Container image build ran successfully to completion!")
            if args.push:
                buildcontainerimage.push_image(
                    dry_run=args.dry_run,
                )
            if args.list_registry:
                buildcontainerimage.list_registry_image_labels()
            if args.pull:
                if not buildcontainerimage.pull_image(
                        dry_run=args.dry_run,
                ):
                    sys.exit(1)
            if args.show_hash:
                buildcontainerimage.show_hash()
        except ValueError as e:
            print(e)
            sys.exit(1)
