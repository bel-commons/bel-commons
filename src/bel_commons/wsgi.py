# -*- coding: utf-8 -*-

"""Run BEL Commons as a WSGI application.

Run with GUnicorn: ``gunicorn -w 4 -b 0.0.0.0:5000 bel_commons.wsgi:app``
"""

import logging

from bel_commons.application import create_application

datefmt = '%H:%M:%S'
fmt = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

level = logging.INFO
logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

logging.getLogger('pybel').setLevel(level)
logging.getLogger('pybel_tools').setLevel(level)
logging.getLogger('bel_commons').setLevel(level)

app = create_application()
