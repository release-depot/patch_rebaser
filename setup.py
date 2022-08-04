#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

requirements = [ 'Distroinfo>=0.1,<=0.5.1',
                 'git_wrapper>=0.2.2,<=0.2.8' ]

test_requirements = [ 'mock', 'pytest', ]

setup(
    author="Release Depot",
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    description="DLRN custom pre-processing script to automatically rebase patches on top of incoming repo changes.",
    install_requires=requirements,
    license="MIT license",
    long_description=readme,
    include_package_data=True,
    keywords='patch_rebaser',
    name='patch_rebaser',
    packages=find_packages(include=['patch_rebaser']),
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/release-depot/patch_rebaser',
    version='0.1.0',
    zip_safe=False,
)
