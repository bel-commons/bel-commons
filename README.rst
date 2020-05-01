BEL Commons |build| |docs|
==========================
An environment for curating, validating, and exploring knowledge assemblies
encoded in Biological Expression Language (BEL) to support elucidating
disease-specific, mechanistic insight.

Installation
~~~~~~~~~~~~
BEL Commons can be installed easily from `PyPI <https://pypi.python.org/pypi/bel_commons>`_ with the following code in
your favorite shell:

.. code-block:: sh

    $ pip install bel_commons

Get the latest code on `GitHub <https://github.com/bel-commons/bel-commons>`_
with:

.. code-block:: sh

    $ python3 -m pip install git+https://github.com/bel-commons/bel-commons.git

It's also suggested to use a relational database management system like PostgreSQL
and install their corresponding connectors:

.. code-block:: sh

    $ python3 -m pip install psycopg2-binary

Usage
-----
Run BEL Commons
~~~~~~~~~~~~~~~
A test server can be easily run with:

.. code-block:: sh

    $ bel-commons run

A more powerful server like ``gunicorn`` can also be used like:

.. code-block:: sh

    $ gunicorn bel_commons.wsgi:flask_app

Running with the Parser
~~~~~~~~~~~~~~~~~~~~~~~
To run the parser, you'll need an instance of a message queue like `RabbitMQ <https://www.rabbitmq.com>`_ (or
any other message queue supported by `Celery <https://pypi.python.org/pypi/celery>`_), a results backend like
`Redis <https://redis.io/>`_, and a worker. It's best to run in docker if you want to do this.

Run with Docker
~~~~~~~~~~~~~~~
Clone this repo from GitHub

.. code-block:: sh

   $ git clone https://github.com/bel-commons/bel-commons.git
   $ cd bel-commons

Create a file called ``.env`` and generate both ``SECRET_KEY`` and ``SECURITY_PASSWORD_SALT``.

.. code-block:: sh

    SECRET_KEY=mypassword
    SECURITY_PASSWORD_SALT=mypassword
    BUTLER_NAME="BEL Commons Butler"
    BUTLER_EMAIL=bel@example.com
    BUTLER_PASSWORD=butlerpassword

If you want to run BEL Commons so networks can be made private, then add ``DISALLOW_PRIVATE=false``. More
documentation on what setting are possible can be found in

Run docker compose:

.. code-block:: sh

    $ docker-compose up

Ports exposed:

- 5002: BEL Commons web application
- 5432: PostgreSQL database

Check the logs with:

.. code-block:: bash

    docker exec -it <your container id> /usr/bin/tail -f web_log.txt

Make an existing user an admin with:

.. code-block:: bash

    docker exec -it <your container id> bel-commons manage users make-admin <user email>

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
