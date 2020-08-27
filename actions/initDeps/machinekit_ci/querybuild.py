#!/usr/bin/env python3
"""
Script to query the Machinekit CI YAML configuration
"""

import argparse
import sh
import os
import sys
import json
import yaml
import machinekit_ci.script_helpers as helpers

class Query(helpers.DistroSettings):
    _query_keys = set()
    def __init__(self: object, path, version, architecture):
        super(Query, self).__init__(path, version, architecture)
        self._hash_os_distros()

        if 'GITHUB_CONTEXT' in os.environ:
            with io.StringIO(os.environ['GITHUB_CONTEXT']) as f:
                self._github_context = json.load(f)

    def _hash_os_distros(self):
        # Create dicts of the `osDistros` config with release and codename as keys
        self._os_distro_dict = {d['osRelease']:d for d in self.distro_settings['osDistros']}
        self._os_distro_dict.update({d['codename']:d for d in self.distro_settings['osDistros']})

        # Create matrix dict
        self._matrix_dict = {
            (c['architecture'],c['osRelease']):self._os_distro_dict[c['osRelease']].copy()
            for c in self.distro_settings['allowedCombinations']
        }
        for k, v in self._matrix_dict.items():
            # Add architecture and lower-case vendor
            v['architecture'] = k[0]
            v['vendorLower'] = v['vendor'].lower()


    class _query_property:
        query_keys = dict()

        def __init__(self, prop_func):
            self.prop_func = prop_func
            self.doc = prop_func.__doc__

        def __set_name__(self, owner, name):
            self.query_keys[self.prop_func.__name__] = self.doc
            setattr(owner, name, property(self.prop_func))

    @_query_property
    def github_main_matrix(self):
        '''Main matrix used in GitHub Actions'''
        return dict(include=list(self._matrix_dict.values()))

    @_query_property
    def github_os_matrix(self):
        '''OS matrix used in GitHub Actions'''
        distros = self.distro_settings['osDistros'].copy()
        updates = self.distro_settings.copy()
        updates.pop('osDistros')
        updates.pop('allowedCombinations')
        for d in distros:
            d.update(updates)
        return distros

    @_query_property
    def docker_images(self):
        '''List of Docker images'''
        images = list()
        for architecture, release in self._matrix_dict.keys():
            self.set_os_arch_combination(release, architecture)
            images.append(self.image_name)
        return images


    def list_keys(self):
        for k, doc in self._query_property.query_keys.items():
            print("{}:  {}".format(k, doc))

    def run_query(self, query_key, format="auto", pretty=False):
        if not hasattr(self, query_key):
            raise RuntimeError('No such query key "{}"'.format(query_key))
        value = getattr(self, query_key)
        if format == "auto":
            format = "json" if type(value) in (list, dict) else "str"
        if format == "str":
            print(str(value))
        elif format == "json":
            kwargs = dict(indent=2) if pretty else dict()
            print(json.dumps(value, **kwargs))
        elif format == "yaml":
            print(yaml.dump(value, default_flow_style=False))
        else:
            raise RuntimeError("Unknown format '{}'".format(format))

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Query distro YAML and Github context")

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=helpers.PathExistsAction,
                            help="Path to root of git repository")
        parser.add_argument("--version",
                            help="OS version number or codename")
        parser.add_argument("--architecture",
                            help="Debian architecture")
        parser.add_argument("--list-keys",
                            action="store_true",
                            help="List all keys")
        parser.add_argument("--format",
                            choices=["str", "json", "yaml"],
                            default="auto",
                            help="Output format (default: 'json' for objects, else 'str')")
        parser.add_argument("--pretty",
                            action="store_true",
                            help="Output in human-readable format")

        # Positional arguments
        parser.add_argument("query_keys",
                            metavar="QUERY_KEYS",
                            nargs=argparse.REMAINDER,
                            help="Key to query")

        args = parser.parse_args()
        query_obj = cls(path=args.path, version=args.version, architecture=args.architecture)
        if args.list_keys:
            query_obj.list_keys()
        elif args.query_keys:
            for query_key in args.query_keys:
                query_obj.run_query(query_key, format=args.format, pretty=args.pretty)
