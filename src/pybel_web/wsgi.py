# -*- coding: utf-8 -*-

"""Run BEL Commons as a WSGI application.

Run with GUnicorn: ``gunicorn -w 4 -b 0.0.0.0:5000 pybel_web.wsgi:app``
"""

import logging

from pybel_web.application import create_application

datefmt = '%H:%M:%S'
fmt = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

level = logging.INFO
logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

pybel_log = logging.getLogger('pybel')
pybel_log.setLevel(level)

pbt_log = logging.getLogger('pybel_tools')
pbt_log.setLevel(level)

pbw_log = logging.getLogger('pybel_web')
pbw_log.setLevel(level)

app = create_application()

pbw_log.info('done creating app')
