Installation
============
This application runs on Python 3.7+.

Database
--------
For production, it is preferred to use a multi-threading relational database
management system. PyBEL has been best tested on PostgreSQL, so this is
preferred for now.

Message Broker
--------------
This application uses `Celery <https://pypi.python.org/pypi/celery>`_ as a
task management system to support asynchronous parsing of BEL documents,
running of analyses, and other slow operations.

RabbitMQ, or any other message queue supported by Celery are appropriate.

Server
------
Because this application is built with Flask, it can be run with the WSGI
protocol. Running on a single machine is possible with either the built-in
``werkzeug`` test server or something easy to install like ``gunicorn``.

For production, ``uwsgi`` seems to work pretty well.
