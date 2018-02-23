Running with Docker
===================
Docker is very powerful as a general way to specify how things should be installed, but has a steep learning curve.
After installing and running ``docker-machine`` and ``docker-compose``, BEL Commons can be run with a few simple
commands.

Dockerfile
----------
A simple Dockerfile is included at the root-level of the repository. This Dockerfile is inspired by the tutorials from
`Container Tutorials <http://containertutorials.com/docker-compose/flask-simple-app.html>`_ and
`Digital Ocean <https://www.digitalocean.com/community/tutorials/docker-explained-how-to-containerize-python-web-applications>`_.

.. warning::

    - The virtual machine needs at least 2GB memory for the worker container
    - The database needs a packet size big enough to accommodate large BEL files (>10 mb)
