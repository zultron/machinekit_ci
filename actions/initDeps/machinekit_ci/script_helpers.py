#!/usr/bin/env python3
# # -*- coding: utf-8 -*-

#####################################################################
# Description:  script_helpers.py
#
#               This file, 'script_helpers.py', implements all common
#               functions used in Python maintenance scripts for CI
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

import argparse
import os
import sh
import yaml
import math
from urllib.parse import urlparse

# Debian 9 Stretch, Ubuntu 18.04 Bionic and (probably) other older distributions
# need in environment LANG=C.UTF-8 (or other similar specification of encoding)
# to properly function


class PathExistsAction(argparse.Action):
    def test_path(self: object, path) -> str:
        if not os.path.isdir(path):
            raise argparse.ArgumentError(self,
                                         "Path {} does not exist.".format(path))
        if not os.access(path, os.W_OK):
            raise argparse.ArgumentError(self,
                                         "Path {} cannot be written to.".format(path))
        return os.path.realpath(os.path.abspath(path.rstrip(os.sep)))

    def __call__(self, parser, namespace, values, option_string=None):
        if type(values) == list:
            folders = map(self.test_path, values)
        else:
            folders = self.test_path(values)

        setattr(namespace, self.dest, folders)


class HostArchitectureValidAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        try:
            sh.dpkg_architecture("-a", values, _tty_out=False)
        except sh.ErrorReturnCode:
            raise argparse.ArgumentError(self,
                                         "Architecture {} is a not valid DPKG one.".format(values))
        setattr(namespace, self.dest, values)


class NormalizePath():
    def __init__(self: object, path):
        self.path = self.path_raw = path
        self.root_path = ""

    def normalize_path(self: object) -> None:
        self.path = os.path.normpath(self.path_raw)

    def verify_path_exists(self: object) -> None:
        if not os.path.exists(self.path):
            error_message = "Path {} is not a file or directory.".format(
                self.path)
            raise ValueError(error_message)

    def version_file_valid(self: object) -> bool:
        version_file = "{}/VERSION".format(self.root_path)

        if not os.path.isfile(version_file):
            return False
        with open(version_file, "r") as reader:
            version_string = reader.read()
        if version_string:
            return True

    def is_repository_root(self: object) -> bool:
        return self.version_file_valid()

    def getGitRepositoryRoot(self: object) -> None:
        try:
            self.root_path = sh.git("rev-parse",
                                    "--show-toplevel",
                                    _tty_out=False,
                                    _cwd=self.path).strip().rstrip(os.sep)
        except sh.ErrorReturnCode as e:
            error_message = "Path {} is not a git repository. Error {}".format(
                self.path, e)
            raise ValueError(error_message)

    def __call__(self: object) -> str:
        self.verify_path_exists()
        self.getGitRepositoryRoot()
        if self.is_repository_root():
            return self.root_path
        else:
            error_message = "Path {} is not a git repository.".format(
                self.path)
            raise ValueError(error_message)

class NormalizeSubdir(NormalizePath):
    def __init__(self: object, *paths):
        self.path_raw = os.path.join(*paths)
        self.normalize_path()

    def check_writable(self: object) -> bool:
        return os.access(self.path, os.W_OK)

    def __call__(self: object) -> str:
        self.verify_path_exists()
        return self.path

class DistroSettings(object):
    yaml_file = "debian-distro-settings.yaml"
    # Optional file for providing environment settings outside of CI
    local_env_file = "local-env.yaml"

    def __init__(self: object, path: str, version=None, host_architecture=None):
        # Set up paths
        if not path:
            path = os.getcwd()
        self.normalized_path = NormalizePath(path)()
        self.github_dir = NormalizeSubdir(self.normalized_path, '.github')()
        self.read_distro_settings()
        self.read_local_env()

        if version and host_architecture:
            self.set_os_arch_combination(version, host_architecture)
        else:
            self.os_arch_is_set = False

    def read_distro_settings(self: object):
        self.yaml_path = os.path.join(self.github_dir, self.yaml_file)
        if not os.path.exists(self.yaml_path):
            error_message = "Config file '{}' not found".format(
                self.yaml_path)
            raise ValueError(error_message)
        with open(self.yaml_path, "r") as reader:
            self.distro_settings = yaml.safe_load(reader)

    def read_local_env(self: object):
        self.local_env_path = os.path.join(self.github_dir, self.local_env_file)
        if not os.path.exists(self.local_env_path):
            return
        with open(self.local_env_path, "r") as reader:
            self.local_env_settings = yaml.safe_load(reader)
        for key, value in self.local_env_settings.items():
            # Set environment variables; don't clobber
            if key not in os.environ:
                os.environ[key] = value

    def env(self, var, default=None):
        # Check and return environment variable; raise exception if not found
        value = os.environ.get(var,None)
        if value is not None:
            return value
        if default is None:
            raise RuntimeError("{} unset in environment".format(var))
        return default

    @property
    def package(self):
        return self.distro_settings['package']

    @property
    def label_prefix(self):
        return self.distro_settings.get(
            'label_prefix', 'io.machinekit.{}'.format(self.package))

    @property
    def project_name(self):
        return self.distro_settings['projectName']

    @property
    def docker_context_path(self):
        # Absolute path to docker context (default '$PWD')
        return os.path.join(
            self.normalized_path, self.distro_settings.get('docker_context_path','.'))

    @property
    def source_dir(self):
        # Path to package sources; usually the same as self.normalized_path, but
        # can be a subdirectory
        return NormalizeSubdir(
            self.normalized_path, self.distro_settings.get('sourceDir','.'))()

    @property
    def debian_dir(self):
        # Relative path to debian/ directory (default 'debian/')
        return self.distro_settings.get('debian_dir','debian')

    @property
    def script_pre_cmd(self):
        # Command to run to configure debian image before installing build deps
        return self.distro_settings.get('scriptPreCmd',None)

    @property
    def script_post_cmd(self):
        # Command to run to configure debian image after installing build deps
        return self.distro_settings.get('scriptPostCmd',None)

    @property
    def configure_src_cmd(self):
        # Command to run to configure soruce tree before package build
        return self.distro_settings.get('configureSourceCmd',None)

    @property
    def parent_dir(self):
        return NormalizeSubdir(os.path.join(self.normalized_path, '..'))()

    def assert_parent_dir_writable(self: object):
        parent_dir = NormalizeSubdir(os.path.join(self.normalized_path, '..'))
        if not parent_dir.check_writable():
            raise ValueError(
                "Directory {0} is not writable.".format(parent_directory()))

    def template(self: object, format: str) -> str:
        replacements = dict(
            PACKAGE = self.package,
            VENDOR = self.vendor,
            ARCHITECTURE = self.architecture,
            OSRELEASE = self.os_release,
        )
        result = format
        for key, val in replacements.items():
            result = result.replace("@{}@".format(key), val)
        return result

    @property
    def image_name(self):
        if getattr(self, "image_name_override", None):  # Allow overriding template
            return self.image_name_override
        self.assert_os_arch_is_set()
        image_name_fmt = self.distro_settings.get(
            'imageNameFmt','@PACKAGE@-@VENDOR@-builder')
        image_name = self.template(image_name_fmt)
        return image_name

    @property
    def image_tag(self):
        self.assert_os_arch_is_set()
        image_tag_fmt = self.distro_settings.get(
            'imageTagFmt','@OSRELEASE@_@ARCHITECTURE@')
        image_tag = self.template(image_tag_fmt)
        return image_tag

    @property
    def docker_registry_namespace(self: object):
        return "{}/{}".format(
            self.env('DOCKER_REGISTRY_USER'), self.env('DOCKER_REGISTRY_REPO'))

    @property
    def image_registry_name_tag(self):
        registry_url = self.env('DOCKER_REGISTRY_URL')
        registry_hostname = urlparse(registry_url).hostname
        return "{}/{}/{}:{}".format(
            registry_hostname, self.docker_registry_namespace,
            self.image_name, self.image_tag)



    def set_os_arch_combination(self: object, version, architecture) -> bool:
        for os_data in self.distro_settings['osDistros']:
            if (os_data['codename'].lower().__eq__(str(version).lower()) or
                 str(os_data['osRelease']).__eq__(version)):
                for combination in self.distro_settings['allowedCombinations']:
                    if (math.isclose(
                            os_data['osRelease'], combination['osRelease'],
                            rel_tol=1e-5) and
                            combination['architecture'].lower().__eq__(architecture.lower())):
                        self.base_image = os_data['baseImage'].lower()
                        self.architecture = combination['architecture'].lower()
                        self.vendor = os_data['vendor'].lower()
                        self.os_release = str(os_data['osRelease'])
                        self.os_codename = os_data['codename'].lower()
                        self.os_arch_is_set = True
                        return True
        return False

    def assert_os_arch_is_set(self: object) -> None:
        if not self.os_arch_is_set:
            error_message = "No OS+arch set"
            raise RuntimeError(error_message)

    @property
    def image_hash_label(self):
        return "{}.image_hash".format(self.label_prefix)
