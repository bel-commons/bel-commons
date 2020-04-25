BEL Commons |build| |docs|
==========================
An environment for curating, validating, and exploring knowledge assemblies
encoded in Biological Expression Language (BEL) to support elucidating
disease-specific, mechanistic insight.

Run with Docker
---------------
Clone this repo from GitHub

.. code-block:: sh

   $ git clone https://github.com/bel-commons/bel-commons.git
   $ cd bel-commons

Create a file called ``.env`` and generate both ``SECRET_KEY`` and ``SECURITY_PASSWORD_SALT``.

.. code-block:: sh

    SECRET_KEY=mypassword
    SECURITY_PASSWORD_SALT=mypassword

Run docker compose:

.. code-block:: sh

    $ docker-compose up

Ports exposed:

- 5002: BEL Commons web application
- 5432: PostgreSQL database

Running Locally
---------------
Software Requirements
~~~~~~~~~~~~~~~~~~~~~
- `Python <https://www.python.org/>`_ 3.7+
- `PostgreSQL <https://www.postgresql.org>`_
- `RabbitMQ <https://www.rabbitmq.com>`_ (or other message queue supported
  by `Celery <https://pypi.python.org/pypi/celery>`_)
- `Redis <https://redis.io/>`_

Hardware Requirements
~~~~~~~~~~~~~~~~~~~~~
At least 2GB RAM for the PyBEL compiler

Installation
~~~~~~~~~~~~
Get the latest code on `GitHub <https://github.com/bel-commons/bel-commons>`_
with:

.. code-block:: sh

    $ python3 -m pip install git+https://github.com/bel-commons/bel-commons.git

It's also suggested to use a relational database management system like MySQL
or PostgreSQL and install their corresponding connectors:

.. code-block:: sh

    $ python3 -m pip install psycopg2-binary


License
-------
This repository is under the `MIT License <https://github.com/bel-commons/bel-commons/blob/master/LICENSE>`_.

Usage
-----
Reset the Database
~~~~~~~~~~~~~~~~~~
For the times when you just have to burn it down and start over:

1. ``bel-commons manage drop`` will nuke the database and output a user list
2. ``bel-commons manage load`` will automatically add the most recently exported
   user list
3. ``bel-commons manage examples load`` will automatically load some example
   networks and data sets

Citation
--------
If you find BEL Commons useful in your work, please consider citing [Hoyt2018]_ and [Hoyt2017]_:

.. [Hoyt2018] Hoyt, C. T., Domingo-Fernández, D., & Hofmann-Apitius, M. (2018). `BEL Commons: an environment for
              exploration and analysis of networks encoded in Biological Expression Language
              <https://doi.org/10.1093/database/bay126>`_. *Database*, 2018(3), 1–11.
.. [Hoyt2017] Hoyt, C. T., Konotopez, A., & Ebeling, C., (2017). `PyBEL: a computational framework for Biological
              Expression Language <https://doi.org/10.1093/bioinformatics/btx660>`_. *Bioinformatics*,
              34(4), 703–704.

Acknowledgements
----------------
Supporters
~~~~~~~~~~
This project has been supported by several organizations:

- `University of Bonn <https://www.uni-bonn.de>`_
- `Bonn Aachen International Center for IT <http://www.b-it-center.de>`_
- `Fraunhofer Institute for Algorithms and Scientific Computing <https://www.scai.fraunhofer.de>`_
- `Fraunhofer Center for Machine Learning <https://www.cit.fraunhofer.de/de/zentren/maschinelles-lernen.html>`_
- `IMI <https://www.imi.europa.eu/>`_ (in the `AETIONOMY <http://www.aetionomy.eu/>`_ project)

Logo
~~~~
The BEL Commons `logo <https://github.com/pybel/pybel-art>`_ was designed by `Scott Colby <https://github.com/scolby33>`_.

.. |build| image:: https://travis-ci.com/bel-commons/bel-commons.svg?branch=master
    :target: https://travis-ci.com/bel-commons/bel-commons
    :alt: Travis-CI Build Status

.. |docs| image:: https://readthedocs.org/projects/bel-commons/badge/?version=latest
    :target: https://bel-commons.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status
