# -*- coding: utf-8 -*-

"""
Data Services
-------------

Each python module in the web submodule should have functions that take a Flask app and add certain endpoints to it. 
These endpoints should expose data as JSON, and not rely on templates, since they should be usable by apps in other
packages and locations
"""

from __future__ import print_function

from .admin_service import build_admin_service
from .analysis_service import analysis_blueprint
from .application import create_application
from .constants import *
from .curation_service import curation_blueprint
from .database_service import api_blueprint
from .main_service import build_main_service
from .models import Role, User
from .parser_async_service import parser_async_blueprint
from .parser_endpoint import build_parser_service
from .upload_service import upload_blueprint

__version__ = '0.1.1'

__title__ = 'pybel_web'
__description__ = 'PyBEL Web'
__url__ = 'https://github.com/pybel/pybel-web'

__author__ = 'Charles Tapley Hoyt'
__email__ = 'cthoyt@gmail.com'

__license__ = 'Apache License 2.0'
__copyright__ = 'Copyright (c) 2016 Charles Tapley Hoyt'
