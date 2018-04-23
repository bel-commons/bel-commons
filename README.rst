BEL Commons
===========
An environment for curating, validating, and exploring knowledge assemblies encoded in Biological Expression Language
(BEL) to support elucidating disease-specific, mechanistic insight.

System Requirements
-------------------
- `Python <https://www.python.org/>`_ 3.4+
- `MySQL <https://www.mysql.com/>`_
- `RabbitMQ <https://www.rabbitmq.com>`_ (or other message queue supported by `Celery <https://pypi.python.org/pypi/celery>`_)
- `uWSGI <https://uwsgi-docs.readthedocs.io/en/latest/>`_

At least 2GB RAM for parsing. Multiple users are expected per day, likely concurrently.

Installation |license|
----------------------
Get the latest code on `GitLab <https://gitlab.scai.fraunhofer.de/charles.hoyt/pybel-web>`_ with:

.. code-block:: sh

    $ python3 -m pip install git+https://gitlab.scai.fraunhofer.de/charles.hoyt/pybel-web.git

It's also suggested to use a relational database management system like MySQL or PostgreSQL and install their
corresponding connectors:

.. code-block:: sh

    $ python3 -m pip install mysqlclient


Create the Database
-------------------
As an example with MySQL-specific SQL:

.. code-block:: sql

    CREATE DATABASE pybel DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;

Do it from bash with extreme prejudice:

.. code-block:: sh

    mysql -u root -e "drop database if exists pybel;CREATE DATABASE pybel DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;"

Phoenix the Database
~~~~~~~~~~~~~~~~~~~~
For the times when you just have to burn it down and start over

1. ``pybel_web manage drop`` will nuke the database and output a user list
2. ``pybel_web manage load`` will automatically add the most recently exported user list
3. ``pybel_web manage examples load`` will automatically load some example networks and data sets

Configuration
-------------
Default configuration can be found in the module ``pybel_web.config``.

By default, PyBEL searches for a configuration file called ``config.json`` in ``~/.config/pybel/``. This directory
can be modified with the environment variable ``PYBEL_CONFIG_DIRECTORY``. Additioanlly, the location of another custom
configuration can be specified by the environment variable ``PYBEL_WEB_CONFIG_JSON``.

In ``config.json`` add an entry ``PYBEL_MERGE_SERVER_PREFIX`` for the address of the server. Example:
``http://lisa:5000`` with no trailing backslash. This is necessary since celery has a problem with flask's url builder
function ``flask.url_for``.

Add an entry ``PYBEL_CONNECTION`` with the database connection string to either a local SQLite database
or a proper relational database management system. It's suggested to ``pip install mysqlclient`` in combination with
MySQL since it enables multi-threading.

For a deployment with a local instance of RabbitMQ, the default configuration already contains a setting for
``amqp://localhost``. Otherwise, an entry ``CELERY_BROKER_URL`` can be set.

Deployment
----------
Server
~~~~~~
The same configurations and procedures are true for both the testing server, lisa.scai.fraunhofer.de, and the
production server, bart.scai.fraunhofer.de. The testing deployment is available internally at
http://pybel-internal.scai.fraunhofer.de and the production deployment is available externally at
https://pybel.scai.fraunhofer.de.

Updating
~~~~~~~~
- update repositories in ``/var/www/pybel/src/``. PyBEL, PyBEL Tools, and BEL Commons are all installed as editable
  in the virtual environment, ``venv``, stored in ``/var/www/pybel/.virtualenvs``
- restart services with the commands:
    - ``sudo systemctl restart uwsgi.service``
    - ``sudo systemctl restart celery.service``

Input
~~~~~
This service accepts BEL Scripts as input through an HTML form. It also has a user registration page that tracks
email addresses and names of users. Its underlying database is populated accordingly.

Acknowledgement
---------------
This package was originally developed with the results from the master's work of
`Charles Tapley Hoyt <https://github.com/cthoyt>`_ at `Fraunhofer SCAI <https://www.scai.fraunhofer.de/>`_ with
partial support from the `IMI <https://www.imi.europa.eu/>`_ projects: `AETIONOMY <http://www.aetionomy.eu/>`_.

.. |license| image:: https://img.shields.io/badge/License-Apache%202.0-blue.svg
    :alt: Apache 2.0 License
