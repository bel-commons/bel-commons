# -*- coding: utf-8 -*-

"""Local proxies for PyBEL Web."""

from pybel_web.core.celery import PyBELCelery
from pybel_web.core.sqlalchemy import PyBELSQLAlchemy

__all__ = [
    'celery',
    'manager',
]

celery = PyBELCelery.get_celery_proxy()
manager = PyBELSQLAlchemy.get_manager_proxy()
