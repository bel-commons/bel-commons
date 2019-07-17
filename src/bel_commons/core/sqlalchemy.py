# -*- coding: utf-8 -*-

"""An extension to Flask-SQLAlchemy."""

from __future__ import annotations

import logging
from typing import Type

from flask import Flask, current_app
from flask_sqlalchemy import SQLAlchemy, get_state
from werkzeug.local import LocalProxy

from pybel import Manager

__all__ = [
    'PyBELSQLAlchemy',
]

log = logging.getLogger(__name__)


class PyBELSQLAlchemy(SQLAlchemy):
    """An extension of Flask-SQLAlchemy to support the BEL Commons manager."""

    #: The class to use to build a manager.
    manager_cls: Type[Manager] = Manager

    #: The actual manager (automatically built)
    manager: manager_cls

    def init_app(self, app: Flask) -> None:
        """Initialize a Flask app."""
        super().init_app(app)

        self.manager = self.manager_cls(engine=self.engine, session=self.session)
        self.manager.bind()

    @classmethod
    def get_manager_proxy(cls) -> Type[Manager]:
        """Get a proxy for the manager from this app."""
        return LocalProxy(cls._get_manager_ca)

    @classmethod
    def _get_manager_ca(cls) -> Type[Manager]:
        return cls.get_manager(current_app)

    @staticmethod
    def get_manager(app: Flask) -> Type[Manager]:
        """Get the manager from this app."""
        return get_state(app).db.manager
