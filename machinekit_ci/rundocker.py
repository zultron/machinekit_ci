#!/usr/bin/env python3
"""
Script for running Machinekit CI commands in Docker
"""

import argparse
import sh
import os
import sys
import machinekit_ci.script_helpers as helpers


class RunDocker(helpers.DistroSettings):
    def __init__(self: object, path, version, architecture, notty, env,
                 volume, docker_args):
        super(RunDocker, self).__init__(path, version, architecture)
        # Use current process std{in,out,err} unless no tty or --notty flag
        self.env_vars = env
        self.volumes = volume
        self.tty = (not notty) and sys.stdout.isatty()
        if docker_args:
            self.docker_args = docker_args
        else:
            self.docker_args = ['--tty', '--interactive'] if self.tty else []
            self.docker_args += [
                "--rm",
                "--user={}:{}".format(os.getuid(), os.getgid()),
                # Mount parent directory where package results will be built
                "--volume={0}:{0}".format(self.parent_dir),
                "--workdir={}".format(self.normalized_path),
                "--hostname={}_{}".format(self.os_codename, self.architecture),
                ]
        # print("path: {}".format(self.path))
        # print("version: {}".format(self.os_codename))
        # print("architecture: {}".format(self.architecture))
        # print("docker_args: {}".format(self.docker_args))

    def run_cmd(self: object, cmd: list):
        docker_args = list(self.docker_args) # Don't modify original list
        if self.env_vars:
            docker_args.extend(['--env={}'.format(e) for e in self.env_vars])
        if self.volumes:
            docker_args.extend(['--volume={}:{}'.format(v,v) for v in self.volumes])
        docker_args.append(self.image_registry_name_tag)
        docker_args.extend(cmd)
        kwargs = dict(
            _cwd=self.normalized_path,
        )
        if self.tty:
            kwargs.update(dict(_fg=True))
        else:
            kwargs.update(dict(_out=sys.stdout.buffer, _err=sys.stderr.buffer))
        sys.stderr.write("sh.docker.run args: {}\n".format(kwargs))
        sys.stderr.write("Running: 'docker' 'run' '{}'\n".format("' '".join(docker_args)))
        try:
            sh.docker.run(*docker_args, **kwargs)
        except sh.ErrorReturnCode as e:
            raise ValueError(
                "'docker run {}' failed:\n".format(' '.join(cmd), e))

    @classmethod
    def cli(cls):

        parser = argparse.ArgumentParser(
            description="Run commands in a builder container",
            epilog="""Args to the 'docker run' command my be supplied before VERSION;
              in this case, add '--' after ARCHITECTURE; e.g.
              "rundocker.py --interactive --env=FOO=BAR --user=1000:1000 20.04 arm64
                  -- bash -c 'echo $FOO'" """,
        )

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=helpers.PathExistsAction,
                            default=os.getcwd(),
                            help="Path to root of git repository")
        parser.add_argument("--notty",
                            action="store_true",
                            help="Do NOT set 'docker run -tty' arg")
        parser.add_argument("--env",
                            action="append",
                            help="Pass or set environment variable in container; see docker-run(1)",
        )
        parser.add_argument("--volume",
                            action="append",
                            help="Bind-mount directory in container; see docker-run(1)",
        )

        # Positional arguments
        parser.add_argument("version",
                            metavar="VERSION",
                            help="OS version number or codename")
        parser.add_argument("architecture",
                            action=helpers.HostArchitectureValidAction,
                            default=sh.dpkg_architecture(
                                "-qDEB_HOST_ARCH",
                                _tty_out=False).strip(),
                            metavar="ARCHITECTURE",
                            help="Debian architecture")
        parser.add_argument("command",
                            metavar="COMMAND",
                            nargs=argparse.REMAINDER,
                            help="Command to run in container")

        args, docker_args = parser.parse_known_args()
        args_dict = args.__dict__
        path = args_dict.pop('path')
        env = args_dict.pop('env')
        volume = args_dict.pop('volume')
        notty = args_dict.pop('notty')
        version = args_dict.pop('version')
        architecture = args_dict.pop('architecture')
        cmd = args_dict.pop('command')
        rd = cls(path=path, version=version,
                       architecture=architecture, notty=notty, env=env,
                       volume=volume, docker_args=docker_args)
        try:
            rd.run_cmd(cmd)
        except ValueError as e:
            sys.stderr.write("Error:  Command exited non-zero:  {}\n".format(str(e)))
