# -*- coding: utf-8 -*-

"""Local proxies for PyBEL Web."""

from flask import current_app
from werkzeug.local import LocalProxy

from pybel_web.core.sqlalchemy import PyBELSQLAlchemy
from pybel_web.manager import WebManager

__all__ = [
    'manager',
    'celery',
]


def get_manager_proxy():
    """Get a proxy for the manager in the current app.

    Why make this its own function? It tricks type assertion tools into knowing that the LocalProxy object represents
    a WebManager.
    """
    return LocalProxy(lambda: PyBELSQLAlchemy.get_manager(current_app))


manager: WebManager = get_manager_proxy()


def get_celery_proxy():
    """Get a proxy for the celery instance in the current app."""
    from pybel_web.core.celery import PyBELCelery

    return LocalProxy(lambda: PyBELCelery.get_celery(current_app))


celery = get_celery_proxy()
