Configuration
=============
Default configuration can be found in the module ``bel_commons.config``.

By default, PyBEL searches for a configuration file called ``config.json``
in ``~/.config/pybel/``. This directory can be modified with the environment
variable ``PYBEL_CONFIG_DIRECTORY``. Additioanlly, the location of another
custom configuration can be specified by the environment variable
``BEL_COMMONS_CONFIG_JSON``.

In ``config.json`` add an entry ``PYBEL_MERGE_SERVER_PREFIX`` for the address
of the server. Example: ``http://lisa:5000`` with no trailing backslash. This
is necessary since celery has a problem with flask's url builder function
``flask.url_for``.

Add an entry ``PYBEL_CONNECTION`` with the database connection string to either
a local SQLite database or a proper relational database management system. It's
suggested to ``pip install psycopg2-binary`` in combination with MySQL since it
enables multi-threading.

For a deployment with a local instance of RabbitMQ, the default configuration
already contains a setting for ``amqp://localhost``. Otherwise, an entry
``CELERY_BROKER_URL`` can be set.


.. autoclass:: bel_commons.config.Config
    :members:
