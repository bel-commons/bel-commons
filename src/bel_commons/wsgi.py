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
from bel_commons.constants import MAIL_DEFAULT_SENDER, SENTRY_DSN, SQLALCHEMY_DATABASE_URI
from bel_commons.converters import IntListConverter, ListConverter
from bel_commons.core import butler, manager, user_datastore
from bel_commons.database_service import api_blueprint
from bel_commons.ext import bio2bel, bootstrap, db, mail, security, swagger
from bel_commons.forms import ExtendedRegisterForm
from bel_commons.main_service import ui_blueprint
from bel_commons.utils import send_startup_mail
from bel_commons.views import (
    curation_blueprint, experiment_blueprint, help_blueprint,
    receiving_blueprint, reporting_blueprint,
)

__all__ = [
    'flask_app',
    'celery_app',
]

logger = logging.getLogger(__name__)

log_path = 'web_log.txt'
fh = logging.FileHandler(log_path)
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)

logger.info('logging to %s', log_path)

flask_app = Flask(__name__)
flask_app.config.update(BELCommonsConfig.load_dict())

# Add converters
flask_app.url_map.converters.update({
    'intlist': IntListConverter,
    'list': ListConverter,
})

logger.info('Initializing Bootstrap (%s)', bootstrap.__class__)
bootstrap.init_app(flask_app)

logger.info('Initializing Swagger (%s)', swagger.__class__)
swagger.init_app(flask_app)

logger.info('Initializing Database (%s)', db.__class__)
db.init_app(flask_app)

logger.info('Initializing Bio2BEL (%s)', bio2bel.__class__)
bio2bel.init_app(flask_app)

if not flask_app.config.get('USE_CELERY'):
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

mail_server = flask_app.config.get('MAIL_SERVER')
if mail_server is not None:
    logger.info('using mail server: %s', mail_server)

    # Set Mail defaults
    flask_app.config.setdefault(
        MAIL_DEFAULT_SENDER,
        (
            flask_app.config['MAIL_DEFAULT_SENDER_NAME'],
            flask_app.config['MAIL_DEFAULT_SENDER_EMAIL'],
        ),
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

if flask_app.config.get('REGISTER_TRANSFORMATIONS'):
    with flask_app.app_context():
        register_transformations(manager=manager)

register_users_path = flask_app.config.get('REGISTER_USERS')
if register_users_path is not None:
    with open(register_users_path) as file:
        manifest = json.load(file)
    with flask_app.app_context():
        register_users_from_manifest(
            user_datastore=user_datastore,
            manifest=manifest,
        )

if flask_app.config.get('REGISTER_EXAMPLES'):
    with flask_app.app_context():
        register_examples(
            manager=manager,
            user_datastore=user_datastore,
            user_id=butler.id,
        )

if flask_app.config.get('REGISTER_ADMIN'):
    with flask_app.app_context():
        register_admin_service(
            app=flask_app,
            manager=manager,
        )

""" Register blueprints"""

if flask_app.config['LOCKDOWN']:
    logger.info('running in lockdown mode')

flask_app.register_blueprint(ui_blueprint)
flask_app.register_blueprint(help_blueprint)
flask_app.register_blueprint(api_blueprint)
flask_app.register_blueprint(reporting_blueprint)

if flask_app.config.get('ENABLE_CURATION'):
    flask_app.register_blueprint(curation_blueprint)

if flask_app.config.get('USE_CELERY'):  # Requires celery!
    logger.info('registering celery-specific apps')
    flask_app.register_blueprint(receiving_blueprint)

    if flask_app.config.get('ENABLE_UPLOADER'):
        logger.info('registering uploading app')
        from bel_commons.views import uploading_blueprint

        flask_app.register_blueprint(uploading_blueprint)

    if flask_app.config.get('ENABLE_ANALYSIS'):
        flask_app.register_blueprint(experiment_blueprint)

if flask_app.config.get('ENABLE_PARSER'):
    logger.info('registering parser app')
    from bel_commons.views import build_parser_service

    build_parser_service(flask_app)

if __name__ == '__main__':
    flask_app.run()
