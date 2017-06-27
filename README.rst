PyBEL Web
=========

Deployment
----------

Server Map
~~~~~~~~~~
- pybel.scai.fraunhofer.de:80 points to bart:5000
- dev.pybel.scai.fraunhofer.de:80 points to bart:5001

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

Phoenix the Database
--------------------
1. ``pybel_web manage drop`` will nuke the database and output a user list
2. ``pybel_web manage load`` will automatically add the most recently exported user list

Setting up with Docker
----------------------
A simple Dockerfile is included at the root-level of the respository. This Dockerfile is inspired by the tutorials
`here <http://containertutorials.com/docker-compose/flask-simple-app.html>`_ and
`here <https://www.digitalocean.com/community/tutorials/docker-explained-how-to-containerize-python-web-applications>`_.

Links
~~~~~

- Running docker on mac: https://penandpants.com/2014/03/09/docker-via-homebrew/
- Using baseimage: http://phusion.github.io/baseimage-docker/
