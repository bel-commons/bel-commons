# -*- coding: utf-8 -*-

"""Celery utils for PyBEL."""

from typing import Optional

from celery import Celery
from celery.result import AsyncResult
from flask import Blueprint, Flask, current_app, jsonify
from werkzeug.local import LocalProxy

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
        self.blueprint = Blueprint('task', __name__, url_prefix='/api/task')

        @self.blueprint.route('/task/<uuid>', methods=['GET'])
        def check(uuid: str):
            """Check the given task.

            :param uuid: The task's UUID as a string
            ---
            parameters:
              - name: uuid
                in: path
                description: The task's UUID as a string
                required: true
                type: string
            responses:
              200:
                description: JSON describing the state of the task
            """
            task = AsyncResult(uuid, app=self._get_celery_ca())

            return jsonify(
                task_id=task.task_id,
                status=task.status,
                result=task.result,
            )

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        """Initialize the app with a Celery instance."""
        app.extensions['celery'] = _create_celery(app)
        app.register_blueprint(self.blueprint)

    @classmethod
    def get_celery_proxy(cls):
        """Get a proxy for the Celery instance from this app."""
        return LocalProxy(cls._get_celery_ca)

    @classmethod
    def _get_celery_ca(cls) -> Celery:
        return cls.get_celery(current_app)

    @staticmethod
    def get_celery(app: Flask) -> Celery:
        """Get the Celery instance that goes with this app."""
        assert 'celery' in app.extensions
        return app.extensions['celery']


def _create_celery(app: Flask) -> Celery:
    """Configure celery instance from application, using its config."""
    backend = app.config.get(CELERY_RESULT_BACKEND)
    if backend is None:
        backend = f'db+{app.config[SQLALCHEMY_DATABASE_URI]}'

    celery = Celery(
        app.import_name,
        broker=app.config[CELERY_BROKER_URL],
        backend=backend,
    )

    celery.conf.update(app.config)

    return celery
