# -*- coding: utf-8 -*-

"""Celery utils for PyBEL."""

from typing import Optional

from celery import Celery
from flask import Flask

__all__ = [
    'PyBELCelery',
]

#: The name of the configuration option for the Celery broker URL.
CELERY_BROKER_URL = 'CELERY_BROKER_URL'
CELERY_RESULT_BACKEND = 'CELERY_RESULT_BACKEND'
SQLALCHEMY_DATABASE_URI = 'SQLALCHEMY_DATABASE_URI'


class PyBELCelery:
    """Wrap celery utilities."""

    def __init__(self, app: Optional[Flask] = None):
        self.app = app
        if app is not None:
            self.init_app(app)

    @staticmethod
    def init_app(app: Flask):
        """Initialize the app with a Celery instance."""
        celery = _create_celery(app)
        app.extensions['celery'] = celery

    @staticmethod
    def get_celery(app: Flask) -> Celery:
        """Get the Celery instance that goes with this app."""
        assert 'celery' in app.extensions
        return app.extensions['celery']


def _create_celery(app: Flask) -> Celery:
    """Configure celery instance from application, using its config."""
    celery = Celery(
        app.import_name,
        broker=app.config[CELERY_BROKER_URL],
        backend=app.config.get(CELERY_RESULT_BACKEND) or 'db+{}'.format(app.config[SQLALCHEMY_DATABASE_URI]),
    )

    celery.conf.update(app.config)

    return celery
