======================
Script - Patch Rebaser
======================


.. image:: https://img.shields.io/pypi/v/patch_rebaser.svg
        :target: https://pypi.python.org/pypi/patch_rebaser

.. image:: https://img.shields.io/travis/release-depot/patch_rebaser.svg
        :target: https://travis-ci.org/release-depot/patch_rebaser

DLRN custom pre-processing script to automatically rebase patches on top of incoming repo changes.


* Free software: MIT license

Pre-requisites
--------------

 * DLRN that includes https://softwarefactory-project.io/r/#/c/14929/

To run DLRN with the script:

 * Place `patch_rebaser.py` on the same host. Make sure the file is executable.
 * Place `patch_rebaser.ini` in the same directory as the script. You can use
   `patch_rebaser.ini.example` as a template.
 * Update custom_preprocess= in DLRN's `projects.ini` with full path to the script.

Make sure everything is set up correctly to authenticate with any of
the expect git remotes (SSH keys, SSL certs, host keys, kerberos config, etc).

Credits
-------

This package was created with Cookiecutter_ based on the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
