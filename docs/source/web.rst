Web Services
============

Configuration
-------------

.. autoclass:: pybel_web.config.Config
:members:

Asynchronous Compilation
------------------------
Using the asynchronous backend requires three steps:

1. Run RabbitMQ Server (or whatever broker) with :code:`./rabbitmq-server`
2. Run Celery Worker with ``python3 -m celery -A pybel_tools.web.celery_worker.celery worker``
3. Run PyBEL Web with ``python3 -m pybel_tools web -vv``


Code
----
.. automodule:: pybel_web.main_service
:members:
