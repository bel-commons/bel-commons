# -*- coding: utf-8 -*-

"""Local proxies for PyBEL Web."""

from pybel_web.core.celery import PyBELCelery
from pybel_web.core.flask_bio2bel import FlaskBio2BEL
from pybel_web.core.sqlalchemy import PyBELSQLAlchemy

__all__ = [
    'celery',
    'manager',
    'flask_bio2bel',
]

celery = PyBELCelery.get_celery_proxy()
manager = PyBELSQLAlchemy.get_manager_proxy()
flask_bio2bel = FlaskBio2BEL.get_proxy()
