# -*- coding: utf-8 -*-

"""An extension to Flask-SQLAlchemy."""

from __future__ import annotations

from flask import Flask, current_app
from flask_security import SQLAlchemyUserDatastore
from flask_sqlalchemy import SQLAlchemy
from werkzeug.local import LocalProxy

from bel_commons.manager import WebManager

__all__ = [
    'PyBELSQLAlchemy',
    'manager',
    'user_datastore',
]


class PyBELSQLAlchemy(SQLAlchemy):
    """An extension of Flask-SQLAlchemy to support the BEL Commons manager."""

    def init_app(self, app: Flask) -> None:
        """Initialize a Flask app."""
        super().init_app(app)

        with app.app_context():
            _manager = app.extensions['manager'] = WebManager(engine=self.engine, session=self.session)
            _manager.bind()


def _get_manager() -> WebManager:
    """Get the manager from the app."""
    _manager = current_app.extensions.get('manager')
    if _manager is None:
        raise RuntimeError(
            'The manager was not registered to the app yet.'
            ' Make sure to call PyBELSQLAlchemy.init_app()',
        )
    return _manager


def _get_user_datastore() -> SQLAlchemyUserDatastore:
    return _get_manager().user_datastore


manager = LocalProxy(_get_manager)
user_datastore = LocalProxy(_get_user_datastore)
