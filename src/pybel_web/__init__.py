# -*- coding: utf-8 -*-

"""

Installation
============
This application is written in Python 3. Future releases will be Python 3.6+ only.

Database
--------
For production, it is preferred to use a multi-threading relational database management system. PyBEL has been best
tested on MySQL, so this is preferred for now.

Message Broker
--------------
This application uses `Celery <https://pypi.python.org/pypi/celery>`_ as a task management system to support asynchronous
parsing of BEL documents, running of analyses, and other slow operations.

RabbitMQ, or any other message queue supported by Celery are appropriate.

Server
------
Because this application is built with Flask, it can be run with the WSGI protocol. Running on a single machine is
possible with either the built-in ``werkzeug`` test server or something easy to install like ``gunicorn``.

For production, ``uwsgi`` seems to work pretty well.

"""

__version__ = '0.2.3'

__title__ = 'pybel_web'
__description__ = 'PyBEL Web'
__url__ = 'https://github.com/pybel/pybel-web'

__author__ = 'Charles Tapley Hoyt'
__email__ = 'cthoyt@gmail.com'

__license__ = 'Apache License 2.0'
__copyright__ = 'Copyright (c) 2016-2018 Charles Tapley Hoyt'
