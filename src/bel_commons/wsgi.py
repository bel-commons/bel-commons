# -*- coding: utf-8 -*-

"""Run BEL Commons as a WSGI application.

Run with GUnicorn: ``gunicorn -w 4 -b 0.0.0.0:5000 bel_commons.wsgi:app``
"""

import json
import logging

from flask import Flask

from bel_commons.application_utils import (
    register_admin_service, register_error_handlers, register_examples,
    register_transformations, register_users_from_manifest,
)
from bel_commons.celery_utils import register_celery
from bel_commons.config import BELCommonsConfig
from bel_commons.constants import (
    MAIL_DEFAULT_SENDER, SENTRY_DSN, SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS, SWAGGER, SWAGGER_CONFIG,
)
from bel_commons.converters import IntListConverter, ListConverter
from bel_commons.core import manager, user_datastore
from bel_commons.database_service import api_blueprint
from bel_commons.ext import bio2bel, bootstrap, db, mail, security, swagger
from bel_commons.forms import ExtendedRegisterForm
from bel_commons.main_service import ui_blueprint
from bel_commons.utils import send_startup_mail
from bel_commons.views import (
    curation_blueprint, experiment_blueprint, help_blueprint,
    receiving_blueprint, reporting_blueprint,
)
from pybel.constants import get_cache_connection

__all__ = [
    'bel_commons_config',
    'flask_app',
    'celery_app',
]

logger = logging.getLogger(__name__)

bel_commons_config = BELCommonsConfig.load()

flask_app = Flask(__name__)
flask_app.config.update(bel_commons_config.to_dict())

# Set SQLAlchemy defaults
flask_app.config.setdefault(SQLALCHEMY_TRACK_MODIFICATIONS, False)
flask_app.config[SQLALCHEMY_DATABASE_URI] = get_cache_connection()
logger.info(f'database: {flask_app.config.get(SQLALCHEMY_DATABASE_URI)}')

# Set Swagger defaults
flask_app.config.setdefault(SWAGGER, SWAGGER_CONFIG)

# Add converters
flask_app.url_map.converters.update({
    'intlist': IntListConverter,
    'list': ListConverter,
})

# Initialize extensions
bootstrap.init_app(flask_app)
swagger.init_app(flask_app)
db.init_app(flask_app)
bio2bel.init_app(flask_app)

if not bel_commons_config.USE_CELERY:
    celery_app = None
else:
    from bel_commons.celery_worker import celery_app, celery_blueprint

    CELERY_BROKER_URL = 'CELERY_BROKER_URL'
    CELERY_RESULT_BACKEND = 'CELERY_RESULT_BACKEND'
    backend = flask_app.config.setdefault(CELERY_RESULT_BACKEND, f'db+{flask_app.config[SQLALCHEMY_DATABASE_URI]}')
    register_celery(flask_app=flask_app, celery_app=celery_app)

    # Add blueprint for test jobs
    flask_app.register_blueprint(celery_blueprint)

""" Initialize Security """

if bel_commons_config.MAIL_SERVER is not None:
    logger.info(f'using mail server: {bel_commons_config.MAIL_SERVER}')

    # Set Mail defaults
    flask_app.config.setdefault(
        MAIL_DEFAULT_SENDER,
        ("BEL Commons", 'bel-commons@scai.fraunhofer.de'),
    )

    mail.init_app(flask_app)
    send_startup_mail(flask_app)

security.init_app(
    app=flask_app,
    datastore=user_datastore,
    register_form=ExtendedRegisterForm,
)

""" Initialize Sentry """

sentry_dsn = flask_app.config.get(SENTRY_DSN)
if sentry_dsn is not None:
    import raven.contrib.flask

    logger.info(f'initiating Sentry: {sentry_dsn}')
    sentry = raven.contrib.flask.Sentry(flask_app, dsn=sentry_dsn)
else:
    sentry = None

register_error_handlers(flask_app, sentry=sentry)

""" Initialize BEL Commons options """

if bel_commons_config.register_transformations:
    with flask_app.app_context():
        register_transformations(manager=manager)

if bel_commons_config.register_users:
    with open(bel_commons_config.register_users) as file:
        manifest = json.load(file)
    with flask_app.app_context():
        register_users_from_manifest(
            user_datastore=user_datastore,
            manifest=manifest,
        )

if bel_commons_config.register_examples:
    with flask_app.app_context():
        register_examples(
            manager=manager,
            user_datastore=user_datastore,
        )

if bel_commons_config.register_admin:
    with flask_app.app_context():
        register_admin_service(
            app=flask_app,
            manager=manager,
        )

""" Register blueprints"""

flask_app.register_blueprint(ui_blueprint)
flask_app.register_blueprint(help_blueprint)
flask_app.register_blueprint(api_blueprint)
flask_app.register_blueprint(reporting_blueprint)

if bel_commons_config.enable_curation:
    flask_app.register_blueprint(curation_blueprint)

if bel_commons_config.USE_CELERY:  # Requires celery!
    logger.info('registering celery-specific apps')
    flask_app.register_blueprint(receiving_blueprint)

    if bel_commons_config.enable_uploader:
        logger.info('registering uploading app')
        from bel_commons.views import uploading_blueprint

        flask_app.register_blueprint(uploading_blueprint)

    if bel_commons_config.enable_analysis:
        flask_app.register_blueprint(experiment_blueprint)

if bel_commons_config.enable_parser:
    logger.info('registering parser app')
    from bel_commons.views import build_parser_service

    build_parser_service(flask_app)

if __name__ == '__main__':
    flask_app.run()
