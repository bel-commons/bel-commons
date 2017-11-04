PyBEL Web
=========
Configuration
-------------
In ``~/.config/pybel/config.json`` add an entry ``PYBEL_MERGE_SERVER_PREFIX`` for the address of the server. Example:
``http://lisa:5000`` with no trailing backslash. This is necessary since celery has a problem with flask's url builder
function ``flask.url_for``.

Add an entry ``PYBEL_CONNECTION`` with the database connection string. It's suggested to ``pip install mysqlclient``
since it enables multithreading.

Database
--------
Create the database with MySQL-specific SQL:

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

Testing Deployment
------------------
Updating
~~~~~~~~
- log on to lisa.scai.fraunhofer.de
- update repositories in /var/www/pybel/src/. PyBEL, PyBEL Tools, and PyBEL Web are all installed as editable
  in the virtual environment, venv, stored in /var/www/pybel/.virtualenvs
- restart services
    - sudo systemctl restart uwsgi.service
    - sudo systemctl restart celery.service

Access
~~~~~~
This service is accessible at pybel-internal.scai.fraunhofer.de

Production Deployment
---------------------
- External Test Server: https://dev.pybel.scai.fraunhofer.de:80 points to http://bart:5001
- External Production Server: https://pybel.scai.fraunhofer.de:80 points to http://bart:5000

Running from the Command Line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To start, type ``tmux ls`` to see the sessions already opened. Inside each session, either create or attach
a virtual machine.

Celery Worker
~~~~~~~~~~~~~
The point of the Celery worker is to take care of running tasks in separate processes, so things like compilation
and analyses don't cause the server to stall up.

1. Attach the celery worker service with ``tmux attach -t worker``
2. Rerun with ``pybel-web worker`` which basically calls the same as: ``python3 -m celery -A pybel_web.celery_worker.celery worker``
3. Quit the ``tmux`` session with ``ctrl-b`` then ``d``

Flask Application
*****************
The flask app needs to be run at ``0.0.0.0`` to be exposed to the outside. Otherwise, this defaults to localhost and
can only be accessed from on bart. Additionally, logging can be shown with ``-v``. More v's, more logging.

1. Attach the Flask session with ``tmux attach -t runner``
2. Quit with ``ctrl-c``
3. Rerun with ``pybel_web run -vv``. On production, use the ``--with-gunicorn`` option to enable multithreading.
4. Quit the ``tmux`` session with ``ctrl-b`` then ``d``

Running the Development Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Our development address is http://dev.scai.fraunhofer.de. It is proxied to bart:5001.

1. ``tmux a -t pybel_dev_runner``
2. If not already working on the development environment, ``source ~/pybel_web_dev_venv/bin/activate``
3. ``pybel-web run -vv --host "0.0.0.0" --port 5001 --config ~/.config/pybel/pybel_dev_config.json``
4. Quit the ``tmux`` session with ``ctrl-b`` then ``d``

Celery can handle both the development and production at the same time, as far as I can tell

Using Docker Compose
--------------------
A simple Dockerfile is included at the root-level of the repository. This Dockerfile is inspired by the tutorials from
`Container Tutorials <http://containertutorials.com/docker-compose/flask-simple-app.html>`_ and
`Digital Ocean <https://www.digitalocean.com/community/tutorials/docker-explained-how-to-containerize-python-web-applications>`_.

- The virtual machine needs at least 2GB memory for the worker container
- The database needs a packet size big enough to accommodate large BEL files (>10 mb)
