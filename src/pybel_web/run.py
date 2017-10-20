# -*- coding: utf-8 -*-

"""

How to Run PyBEL Web

``gunicorn -w 4 -b 0.0.0.0:5000 pybel_web.run:app``

"""

import logging
import os

from .analysis_service import analysis_blueprint
from .application import create_application
from .bms_service import bms_blueprint
from .constants import BMS_IS_AVAILABLE, log_runner_path
from .curation_service import curation_blueprint
from .database_service import api_blueprint
from .external_services import external_blueprint
from .main_service import build_main_service
from .parser_async_service import parser_async_blueprint
from .parser_endpoint import build_parser_service

datefmt = '%H:%M:%S'
fmt = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

data_path = os.path.join(os.path.expanduser('~'), '.pybel', 'data')
user_dump_path = os.path.join(data_path, 'users.tsv')

fh = logging.FileHandler(log_runner_path)
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter(fmt))

level = 20
logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

pybel_log = logging.getLogger('pybel')
pybel_log.setLevel(level)
pybel_log.addHandler(fh)

pbt_log = logging.getLogger('pybel_tools')
pbt_log.setLevel(level)
pbt_log.addHandler(fh)

pbw_log = logging.getLogger('pybel_web')
pbw_log.setLevel(level)
pbw_log.addHandler(fh)

app = create_application()

build_main_service(app)
app.register_blueprint(curation_blueprint)
app.register_blueprint(parser_async_blueprint)
app.register_blueprint(api_blueprint)
app.register_blueprint(analysis_blueprint)
app.register_blueprint(external_blueprint)

if BMS_IS_AVAILABLE:
    app.register_blueprint(bms_blueprint)

if app.config.get('PYBEL_WEB_PARSER_API'):
    build_parser_service(app)

pbw_log.info('done creating app')
