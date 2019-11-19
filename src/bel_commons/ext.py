# -*- coding: utf-8 -*-

"""Extensions for BEL Commons."""

import flasgger
import flask_bootstrap
import flask_mail
import flask_security

from bel_commons.core import FlaskBio2BEL, PyBELSQLAlchemy

__all__ = [
    'bootstrap',
    'mail',
    'security',
    'swagger',
    'bio2bel',
    'db',
]

bootstrap = flask_bootstrap.Bootstrap()

mail = flask_mail.Mail()

security = flask_security.Security()

swagger = flasgger.Swagger()

bio2bel = FlaskBio2BEL()

db = PyBELSQLAlchemy()
