# Machinekit CI scripts

## To use this in your project
- Copy the files from the `github/` directory to your project repo's
  `.github/` directory
- Customize the`.github/debian-distro-settings.yaml` config file for
  your project
  - Set `package` and `projectName`
  - Add optional `scriptPreCmd`, `scriptPostCmd` and/or
    `configureSourceCmd` scripts to `.github/docker/`
  - Optionally add or remove distro versions to build for, and
    optionally add or remove distro version and architecture
    combinations
- Commit the changes and push them
- Check the "Actions" tab on your GitHub project web page for build
  errors

## Signing packages
The workflow can optionally sign packages:
- Go to the GitHub repo "Settings" tab, "Secrets" section
- Add a GitHub repo secret, `PACKAGE_SIGNING_KEY`, with the ascii key
  pasted from output of `gpg --export-secret-keys --armor`
- For local builds, set `PACKAGE_SIGNING_KEY_ID` in `local-env.yaml`
  (see below)

## Push packages to Cloudsmith
The workflow can optionally push packages to Cloudsmith:
- Add a GitHub repo secret, `CLOUDSMITH_API_KEY`

## Using in a local dev environment
These tools can be run locally.  In your project, copy
`.github/local-env-sample.yaml` to `.github/local-env.yaml` and edit
it as indicated.  DO NOT COMMIT IT TO GIT!  It contains sensitive
secrets and should not ever be shared.

There are three main tools; use the `--help` option
for more information:
- `containerimage`:  Build (or pull or push) a Docker image for a
  particular Debian/Ubuntu release and architecture
- `rundocker`:  Run a command or an interactive shell in one of the
  images
- `buildpackages`:  Usually run inside of `rundocker`, perform various
  packaging functions, most notably, build source and binary packages,
  and sign packages.

To set up a Python virtual environment to run these tools:
```
python3 -m venv /tmp/mk-ci-venv
bash # Start new shell (optional)
source /tmp/mk-ci-venv/bin/activate

git clone https://github.com/zultron/docker-registry-client /tmp/mk-ci-venv/drc
(cd /tmp/mk-ci-venv/drc; python3 setup.py install)

(cd actions/initDeps; python3 setup.py install)
```
