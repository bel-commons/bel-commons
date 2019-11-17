# -*- coding: utf-8 -*-

"""Extensions for BEL Commons."""

import flasgger
import flask_bootstrap
import flask_mail
import flask_security
from flask_security import SQLAlchemyUserDatastore

from bel_commons.core import FlaskBio2BEL, PyBELCelery, PyBELSQLAlchemy as PyBELSQLAlchemyBase
from bel_commons.manager import WebManager

bootstrap = flask_bootstrap.Bootstrap()

mail = flask_mail.Mail()

security = flask_security.Security()

swagger = flasgger.Swagger()

celery = PyBELCelery()

flask_bio2bel = FlaskBio2BEL()


class PyBELSQLAlchemy(PyBELSQLAlchemyBase):
    """An updated PyBELSQLAlchemy using the WebManager."""

    manager_cls = WebManager

    @property
    def user_datastore(self) -> SQLAlchemyUserDatastore:
        """Get the user datastore from this manager."""
        return self._manager.user_datastore


db = PyBELSQLAlchemy()
manager = db.get_manager_proxy()
