BEL Commons
===========
An environment for curating, validating, and exploring knowledge assemblies
encoded in Biological Expression Language (BEL) to support elucidating
disease-specific, mechanistic insight.

Citation
--------
If you find BEL Commons useful in your work, please consider citing [Hoyt2018]_:

.. [Hoyt2018] Hoyt, C. T., Domingo-Fernández, D., & Hofmann-Apitius, M. (2018). `BEL Commons: an environment for
              exploration and analysis of networks encoded in Biological Expression Language
              <https://doi.org/10.1093/database/bay126>`_. *Database*, 2018(3), 1–11.

System Requirements
-------------------
Software
~~~~~~~~
- `Python <https://www.python.org/>`_ 3.7+
- `PostgreSQL <https://www.postgresql.org>`_
- `RabbitMQ <https://www.rabbitmq.com>`_ (or other message queue supported
  by `Celery <https://pypi.python.org/pypi/celery>`_)
- `Redis <https://redis.io/>`_
- `uWSGI <https://uwsgi-docs.readthedocs.io/en/latest/>`_

Hardware
~~~~~~~~
At least 2GB RAM for PyBEL's parser

Installation |license|
----------------------
Get the latest code on `GitHub <https://github.com/bel-commons/bel-commons>`_
with:

.. code-block:: sh

    $ python3 -m pip install git+https://github.com/bel-commons/bel-commons.git

It's also suggested to use a relational database management system like MySQL
or PostgreSQL and install their corresponding connectors:

.. code-block:: sh

    $ python3 -m pip install psycopg2-binary

Reset the Database
~~~~~~~~~~~~~~~~~~
For the times when you just have to burn it down and start over:

1. ``bel-commons manage drop`` will nuke the database and output a user list
2. ``bel-commons manage load`` will automatically add the most recently exported
   user list
3. ``bel-commons manage examples load`` will automatically load some example
   networks and data sets

Input
~~~~~
This service accepts BEL Scripts as input through an HTML form. It also has a
user registration page that tracks email addresses and names of users. Its
underlying database is populated accordingly.

Acknowledgement
---------------
This package was originally developed with the results from the master's work
of `Charles Tapley Hoyt <https://github.com/cthoyt>`_ at `Fraunhofer SCAI <https://www.scai.fraunhofer.de/>`_ with
partial support from the `IMI <https://www.imi.europa.eu/>`_ projects,
`AETIONOMY <http://www.aetionomy.eu/>`_.
