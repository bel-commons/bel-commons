PyBEL Web
=========

Deployment
----------

Servers
~~~~~~~
- Internal Test Server: http://lisa:5000
- External Test Server: https://dev.pybel.scai.fraunhofer.de:80 points to http://bart:5001
- External Production Server: https://pybel.scai.fraunhofer.de:80 points to http://bart:5000

Running from the Command Line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To start, type ``tmux ls`` to see the sessions already opened.

Celery Worker
*************
The point of the Celery worker is to take care of running tasks in separate processes, so things like compilation
and analyses don't cause the server to stall up.

1. Attach the celery worker service with ``tmux attach -t pybel_worker``
2. Quit with ``ctrl-c``
3. Rerun with ``python3 -m celery -A pybel_web.celery_worker.celery worker``
4. Quit the ``tmux`` session with ``ctrl-b`` then ``d``

Flask Application
*****************
The flask app needs to be run at ``0.0.0.0`` to be exposed to the outside. Otherwise, this defaults to localhost and
can only be accessed from on bart. Additionally, logging can be shown with ``-v``. More v's, more logging.

1. Attach the Flask session with ``tmux attach -t pybel_flask``
2. Quit with ``ctrl-c``
3. Rerun with ``python3 -m pybel_web run --host "0.0.0.0" --port 5000 -vv``
4. Quit the ``tmux`` session with ``ctrl-b`` then ``d``

Running the Development Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Our development address is http://dev.scai.fraunhofer.de. It is proxied to bart:5001.

1. ``tmux a -t pybel_dev_runner``
2. If not already working on the development environment, ``source ~/pybel_web_dev_venv/bin/activate``
3. ``pybel-web run -vv --host "0.0.0.0" --port 5001 --config ~/.config/pybel/pybel_dev_config.json``
4. Quit the ``tmux`` session with ``ctrl-b`` then ``d``

Celery can handle both the development and production at the same time, as far as I can tell

Phoenix the Database
--------------------
1. ``pybel_web manage drop`` will nuke the database and output a user list
2. ``pybel_web manage load`` will automatically add the most recently exported user list


Create the database with mysql code:

.. code-block:: sql

    CREATE DATABASE mydb
    DEFAULT CHARACTER SET utf8
    DEFAULT COLLATE utf8_general_ci;

Setting up with Docker
----------------------
A simple Dockerfile is included at the root-level of the respository. This Dockerfile is inspired by the tutorials
`here <http://containertutorials.com/docker-compose/flask-simple-app.html>`_ and
`here <https://www.digitalocean.com/community/tutorials/docker-explained-how-to-containerize-python-web-applications>`_.

- The virtual machine needs at least 2GB memory for the worker container
- The database needs a packet size big enough to accommodate large BEL files (>10 mb)

Links
~~~~~

- Running docker on mac: https://penandpants.com/2014/03/09/docker-via-homebrew/
- Using baseimage: http://phusion.github.io/baseimage-docker/

Getting Data
------------
Before running the service, some data can be pre-loaded in your cache.

Loading Selventa Corpra
~~~~~~~~~~~~~~~~~~~~~~~
The Selventa Small Corpus and Large Corpus are two example BEL documents distributed by the
`OpenBEL framework <https://wiki.openbel.org/display/home/Summary+of+Large+and+Small+BEL+Corpuses>`_. They are good
examples of many types of BEL statements and can be used immediately to begin exploring. Add :code:`-v` for more
logging information during compilation. This is highly suggested for the first run, since it takes a while to cache
all of the namespaces and annotations. This only has to be done once, and will be much faster the second time!

Small Corpus:

.. code-block:: sh

    $ python3 -m pybel_tools ensure small_corpus -v

Large Corpus:

.. code-block:: sh

    $ python3 -m pybel_tools ensure large_corpus -v

Uploading Precompiled BEL
~~~~~~~~~~~~~~~~~~~~~~~~~
A single network stored as a PyBEL gpickle can quickly be uploaded using the following code:

.. code-block:: sh

    $ python3 -m pybel_tools io upload -p /path/to/my_network.gpickle

More examples of getting data into the cache can be found `here <http://pybel-tools.readthedocs.io/en/latest/cookbook.html#getting-data-in-to-the-cache>`_.
