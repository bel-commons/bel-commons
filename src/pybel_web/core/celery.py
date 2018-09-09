# -*- coding: utf-8 -*-

"""Celery utils for PyBEL."""

from typing import Optional

from celery import Celery
from celery.result import AsyncResult
from flask import Flask, jsonify

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

        @app.route('/task/<task>', methods=['GET'])
        def check(task: str):
            """Check the given task.

            :param task: The UUID of a task.
            """
            task = AsyncResult(task, app=celery)

            return jsonify(
                task_id=task.task_id,
                status=task.status,
                result=task.result,
            )

    @staticmethod
    def get_celery(app: Flask) -> Celery:
        """Get the Celery instance that goes with this app."""
        assert 'celery' in app.extensions
        return app.extensions['celery']


def _create_celery(app: Flask) -> Celery:
    """Configure celery instance from application, using its config."""
    if CELERY_RESULT_BACKEND in app.config:
        backend = app.config.get(CELERY_RESULT_BACKEND)
    else:
        backend = 'db+{}'.format(app.config[SQLALCHEMY_DATABASE_URI])

    celery = Celery(
        app.import_name,
        broker=app.config[CELERY_BROKER_URL],
        backend=backend,
    )

    celery.conf.update(app.config)

    return celery
