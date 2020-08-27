#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#####################################################################
# Description:  buildpackages.py
#
#               This file, 'buildpackages.py', implements scripted workflow for
#               building .deb and .ddeb native packages for Debian flavoured
#               distributions.
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
Script for building packages for Debian styled distributions using
'dpkg' family of tools
"""

# Debian 9 Stretch, Ubuntu 18.04 Bionic and (probably) other older distributions
# need in environment LANG=C.UTF-8 (or other similar specification of encoding)
# to properly function

__license__ = "LGPL 2.1"

import argparse
import sh
import os
import sys
import re
import tempfile

import machinekit_ci.script_helpers as helpers
from debian.changelog import Changelog
from debian.deb822 import Changes


class BuildPackages(helpers.DistroSettings):
    def __init__(self: object, path, architecture):
        super(BuildPackages, self).__init__(path)
        self.architecture = architecture
        self.architecture_can_be_build()
        sys.stderr.write("Package directory:  {}\n".format(self.source_dir))
        sys.stderr.write("Host architecture:  {}\n".format(self.architecture))

    def architecture_can_be_build(self: object) -> None:
        build_architectures = sh.dpkg(
            "--print-foreign-architectures", _tty_out=False).strip().split()
        build_architectures.append(sh.dpkg("--print-architecture",
                                           _tty_out=False).strip())
        if self.architecture not in build_architectures:
            raise ValueError(
                "Host architecture {} cannot be built.".format(
                    self.architecture))

    def configure_source(self: object):
        if self.configure_src_cmd is None:
            sys.stderr.write("No configureSourceCmd specified; doing nothing\n")
            return
        self.assert_parent_dir_writable() # May write orig.tar.gz file
        sys.stderr.write("Running configureSourceCmd '{}':\n".format(self.configure_src_cmd))
        try:
            sh.bash('-c', self.configure_src_cmd,
                    _out=sys.stdout.buffer,
                    _err=sys.stderr.buffer,
                    _cwd=self.normalized_path)
        except sh.ErrorReturnCode as e:
            message = "Configure source command '{}' failed:\n{}".format(
                self.configure_src_cmd, e)
            raise ValueError(message)

    def build_packages(self: object):
        self.assert_parent_dir_writable()
        try:
            dpkg_buildpackage_string_arguments = ["-uc",
                                                  "-us",
                                                  "-a",
                                                  self.architecture,
                                                  "-B"]
            if sh.lsb_release("-cs", _tty_out=False).strip().lower() in ["stretch", "bionic"]:
                dpkg_buildpackage_string_arguments.append("-d")
            sh.dpkg_buildpackage(*dpkg_buildpackage_string_arguments,
                                 _out=sys.stdout.buffer,
                                 _err=sys.stderr.buffer,
                                 _cwd=self.source_dir)
        except sh.ErrorReturnCode as e:
            message = "Packages cannot be built because of an error\n{0}".format(
                e)
            raise ValueError(message)

    @property
    def changelog(self: object):
        with open(os.path.join(self.debian_dir, "changelog"), "r") as f:
            changelog = Changelog(f, max_blocks=1)
        return changelog

    @property
    def package_name(self: object):
        return self.changelog[0].package

    @property
    def package_version(self: object):
        # Use as str, or use attributes:
        # full_version epoch upstream_version debian_revision debian_version
        return self.changelog[0].version

    @property
    def source_parent_dir(self: object):
        spd = helpers.NormalizeSubdir(os.path.join(self.source_dir,'..'))
        return spd()

    @property
    def changes_file_path(self: object):
        changes_file = "{}_{}_{}.changes".format(
            self.package_name, self.package_version, self.architecture)
        return os.path.join(self.source_parent_dir, changes_file)

    gpg_home_regex = re.compile(r"^Home:\s*(.*)$", flags=re.MULTILINE)
    def get_gpg_home(self: object):
        gpg_help = str(sh.gpg("--help", _tty_out=False))
        match = self.gpg_home_regex.search(gpg_help)
        return match.group(1)

    def import_gpg_from_secret_env_var(self: object, env_var: str):
        gpg_home = helpers.NormalizeSubdir(self.get_gpg_home())()
        sys.stderr.write("GPG home:  {}\n".format(gpg_home))
        secret = self.env(env_var)
        with tempfile.NamedTemporaryFile(dir=gpg_home, mode='w') as f:
            f.write(secret)
            f.flush()
            sh.gpg("-v", "--batch", "--import", f.name,
                   _out=sys.stdout.buffer,
                   _err=sys.stderr.buffer,
                   _cwd=self.normalized_path)

    def sign_packages(self: object):
        signing_key_id = self.env('PACKAGE_SIGNING_KEY_ID', False)

        source_parent_dir = os.path.join(self.source_dir, '..')
        sh.Command("dpkg-sig")(
            "--sign", "builder", "-v", "-k",
            signing_key_id,
            self.changes_file_path,
            _out=sys.stdout.buffer,
            _err=sys.stderr.buffer,
            _cwd=source_parent_dir)

    def get_package_list(self: object):
        with open(self.changes_file_path, 'r') as f:
            changes = Changes(f)
        return [os.path.join(self.source_parent_dir, f['name'])
                for f in changes['Files']]

    def list_packages(self: object, with_buildinfo=False, with_changes=False):
        for f in self.get_package_list():
            if f.endswith('.buildinfo') and not with_buildinfo:
                continue
            print(f)
        print(self.changes_file_path)


    @classmethod
    def cli(cls):
        """ This is executed when run from the command line """
        parser = argparse.ArgumentParser(
            description="Build packages for Debian like distributions")

        # Default architecture
        default_architecture = os.environ.get(
            "ARCHITECTURE",
            sh.dpkg_architecture(
                "-qDEB_HOST_ARCH",
                _tty_out=False).strip())

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=helpers.PathExistsAction,
                            dest="path",
                            default=os.getcwd(),
                            help="Path to root of git repository")
        parser.add_argument("-a",
                            "--architecture",
                            dest="architecture",
                            action=helpers.HostArchitectureValidAction,
                            default=default_architecture,
                            metavar="ARCHITECTURE",
                            help="Build packages for specific architecture")
        parser.add_argument("--configure-source",
                            action='store_true',
                            help="Run configureSourceCmd to prepare source tree")
        parser.add_argument("--build-packages",
                            action='store_true',
                            help="Build packages")
        parser.add_argument("--import-gpg-from-secret-env-var",
                            help="Import a GPG secret key from the given environment variable")
        parser.add_argument("--sign-packages",
                            action='store_true',
                            help="Sign packages")
        parser.add_argument("--list-packages",
                            action='store_true',
                            help="Print list of package files")
        parser.add_argument("--with-buildinfo",
                            action='store_true',
                            help="With --list-packages, print .buildinfo file")
        parser.add_argument("--with-changes",
                            action='store_true',
                            help="With --list-packages, print .changes file")

        args = parser.parse_args()

        try:
            buildpackages = cls(
                args.path, args.architecture)
            if args.configure_source:
                buildpackages.configure_source()
            if args.build_packages:
                buildpackages.build_packages()
            if args.import_gpg_from_secret_env_var:
                buildpackages.import_gpg_from_secret_env_var(
                    args.import_gpg_from_secret_env_var)
            if args.sign_packages:
                buildpackages.sign_packages()
            if args.list_packages:
                buildpackages.list_packages(args.with_buildinfo, args.with_changes)
        except ValueError as e:
            sys.stderr.write("Error:  Command exited non-zero:  {}\n".format(str(e)))
            sys.exit(1)
