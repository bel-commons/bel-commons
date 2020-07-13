# -*- coding: utf-8 -*-

"""An extension to Flask-SQLAlchemy."""

from __future__ import annotations

import datetime
import logging

from flask import Flask, current_app
from flask_security import SQLAlchemyUserDatastore
from flask_sqlalchemy import SQLAlchemy
from werkzeug.local import LocalProxy

from ..manager import WebManager
from ..models import User

__all__ = [
    'PyBELSQLAlchemy',
    'manager',
    'user_datastore',
]

logger = logging.getLogger(__name__)


class PyBELSQLAlchemy(SQLAlchemy):
    """An extension of Flask-SQLAlchemy to support the BEL Commons manager."""

    def init_app(self, app: Flask) -> None:
        """Initialize a Flask app."""
        super().init_app(app)

        with app.app_context():
            _manager = app.extensions['manager'] = WebManager(engine=self.engine, session=self.session)
            _manager.bind()

            _admin_role = _manager.user_datastore.find_or_create_role('admin')

            _butler_email = app.config['BUTLER_EMAIL']
            _butler: User = _manager.user_datastore.find_user(email=_butler_email)
            if _butler is not None:
                logger.debug('butler user: %s', _butler)
            if _butler is None:
                _butler_name = app.config['BUTLER_NAME']
                _butler_password = app.config['BUTLER_PASSWORD']
                logger.info('creating user: %s (%s)', _butler_name, _butler_email)
                _manager.user_datastore.create_user(
                    email=_butler_email,
                    name=_butler_name,
                    password=_butler_password,
                    active=True,
                    confirmed_at=datetime.datetime.now(),
                )
                _manager.user_datastore.commit()

            _manager.sanitize(user=_butler, public=app.config['DISALLOW_PRIVATE'])

            _admin_email = app.config.get('ADMIN_EMAIL')
            _admin_name = app.config.get('ADMIN_NAME')
            _admin_password = app.config.get('ADMIN_PASSWORD')
            if _admin_email and _admin_name and _admin_password:
                _admin: User = _manager.user_datastore.find_user(email=_admin_email)
                if _admin is None:
                    logger.info('Creating admin: %s (%s)', _admin_name, _admin_email)
                    _admin = _manager.user_datastore.create_user(
                        email=_admin_email,
                        name=_admin_name,
                        password=_admin_password,
                        active=True,
                        confirmed_at=datetime.datetime.now(),
                    )
                    _manager.user_datastore.add_role_to_user(user=_admin, role=_admin_role)
                    _manager.user_datastore.commit()
                logger.debug('admin user: %s (%s)', _admin_name, _admin_email)


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


manager: WebManager = LocalProxy(_get_manager)
user_datastore: SQLAlchemyUserDatastore = LocalProxy(_get_user_datastore)
butler = LocalProxy(lambda: user_datastore.find_user(email=current_app.config['BUTLER_EMAIL']))
