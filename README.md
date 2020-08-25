# Machinekit CI scripts

To use this in your project:
- Copy the files from the `github/` directory to your project repo's
  `.github/` directory
- Customize the`.github/debian-distro-settings.yaml` config file for
  your project
  - Add any scripts as described in the config file to
    `.github/docker/`
- Commit the changes and push them
- Check the "Actions" tab on your GitHub project web page for build
  errors


```
python3 -m venv /tmp/mk-ci-venv
bash # Start new shell
source /tmp/mk-ci-venv/bin/activate

git clone https://github.com/zultron/docker-registry-client /tmp/mk-ci-venv/drc
(cd /tmp/mk-ci-venv/drc; python3 setup.py install)

(cd actions/initDeps; python3 setup.py install)
```
