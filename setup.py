import setuptools

setuptools.setup(
    name="machinekit_ci",
    version="0.0.1",
    author="John Morris",
    author_email="john@zultron.com",
    description="Python utilities used in Machinekit projects CI systems",
    url="https://github.com/zultron/machinekit_ci",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: LGPL 2.1 License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
    entry_points = {
        'console_scripts': [
            'buildpackages=machinekit_ci.buildpackages:BuildPackages.cli',
            'containerimage=machinekit_ci.containerimage:BuildContainerImage.cli',
            'cloudsmithupload=machinekit_ci.cloudsmithupload:CloudsmithUploader.cli',
            'querybuild=machinekit_ci.querybuild:Query.cli',
            'rundocker=machinekit_ci.rundocker:RunDocker.cli',
        ],
    },
    package_data={
        "": ['Dockerfile', 'entrypoint'],
    },
    install_requires=[
        'python-debian',
        'PyYAML',
        'sh',
        'docker_registry_client',
    ],
)
