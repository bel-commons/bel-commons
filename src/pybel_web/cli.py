# -*- coding: utf-8 -*-

"""
Module that contains the command line app

Why does this file exist, and why not put this in __main__?
You might be tempted to import things from __main__ later, but that will cause
problems--the code will get executed twice:
 - When you run `python3 -m pybel_tools` python will execute
   ``__main__.py`` as a script. That means there won't be any
   ``pybel_tools.__main__`` in ``sys.modules``.
 - When you import __main__ it will get executed again (as a module) because
   there's no ``pybel_tools.__main__`` in ``sys.modules``.
Also see (1) from http://click.pocoo.org/5/setuptools/#setuptools-integration
"""

from __future__ import print_function

import datetime
import json
import logging
import os
import sys
import time

import click
from flask_security import SQLAlchemyUserDatastore

from pybel.constants import get_cache_connection
from pybel.manager.cache import build_manager
from pybel.manager.models import Base
from pybel.utils import get_version as pybel_version
from pybel_tools.utils import enable_cool_mode
from pybel_tools.utils import get_version as pybel_tools_get_version
from .constants import log_path
from .admin_service import build_admin_service
from .analysis_service import analysis_blueprint
from .application import create_application
from .curation_service import curation_blueprint
from .database_service import api_blueprint
from .main_service import build_main_service
from .models import Role, User
from .parser_async_service import parser_async_blueprint
from .parser_endpoint import build_parser_service
from .upload_service import upload_blueprint
from .utils import iterate_user_strings

log = logging.getLogger(__name__)

datefmt = '%H:%M:%S'
fmt = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

data_path = os.path.join(os.path.expanduser('~'), '.pybel', 'data')
user_dump_path = os.path.join(data_path, 'users.tsv')

fh = logging.FileHandler(log_path)
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter(fmt))
log.addHandler(fh)


def set_debug(level):
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

    pybel_log = logging.getLogger('pybel')
    pybel_log.setLevel(level)
    pybel_log.addHandler(fh)

    pbt_log = logging.getLogger('pybel_tools')
    pbt_log.setLevel(level)
    pbt_log.addHandler(fh)

    log.setLevel(level)


def set_debug_param(debug):
    if debug == 1:
        set_debug(20)
    elif debug == 2:
        set_debug(10)


@click.group(help="PyBEL-Tools Command Line Interface on {}\n with PyBEL v{}".format(sys.executable, pybel_version()))
@click.version_option()
def main():
    """PyBEL Tools Command Line Interface"""


@main.command()
@click.option('--host', help='Flask host. Defaults to localhost')
@click.option('--port', type=int, help='Flask port. Defaults to 5000')
@click.option('-v', '--debug', count=True, help="Turn on debugging. More v's, more debugging")
@click.option('--flask-debug', is_flag=True, help="Turn on werkzeug debug mode")
@click.option('--config', type=click.File('r'), help='Additional configuration in a JSON file')
def run(host, port, debug, flask_debug, config):
    """Runs PyBEL Web"""
    set_debug_param(debug)
    if debug < 3:
        enable_cool_mode()

    log.info('Running PyBEL v%s', pybel_version())
    log.info('Running PyBEL Tools v%s', pybel_tools_get_version())

    if host is not None:
        log.info('Running on host: %s', host)

    if port is not None:
        log.info('Running on port: %d', port)

    t = time.time()

    config_dict = json.load(config) if config else {}
    app = create_application(**config_dict)

    build_main_service(app)
    build_admin_service(app)
    app.register_blueprint(curation_blueprint)
    app.register_blueprint(parser_async_blueprint)
    app.register_blueprint(upload_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(analysis_blueprint)

    if app.config.get('PYBEL_WEB_PARSER_API'):
        build_parser_service(app)

    log.info('Done building %s in %.2f seconds', app, time.time() - t)

    app.run(debug=flask_debug, host=host, port=port)


@main.group()
@click.option('-c', '--connection', help='Cache connection. Defaults to {}'.format(get_cache_connection()))
@click.pass_context
def manage(ctx, connection):
    """Manage database"""
    ctx.obj = build_manager(connection)
    Base.metadata.bind = ctx.obj.engine
    Base.query = ctx.obj.session.query_property()


@manage.command()
@click.pass_context
def setup(ctx):
    """Creates the database"""
    ctx.obj.create_all()


@manage.command()
@click.option('-f', '--file', type=click.File('r'), default=sys.stdin, help='Input user/role file')
@click.pass_context
def load(ctx, file):
    """Dump stuff for loading later (in lieu of having proper migrations)"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    for line in file:
        email, first, last, roles, password = line.strip().split('\t')
        u = ds.find_user(email=email)

        if not u:
            u = ds.create_user(
                email=email,
                first_name=first,
                last_name=last,
                password=password,
                confirmed_at=datetime.datetime.now()
            )
            log.info('added %s', u)
            ds.commit()
        for role_name in roles.strip().split(','):
            r = ds.find_role(role_name)
            if not r:
                r = ds.create_role(name=role_name)
                ds.commit()
            if not u.has_role(r):
                ds.add_role_to_user(u, r)

    ds.commit()


@manage.command()
@click.pass_context
@click.option('-y', '--yes', is_flag=True)
def drop(ctx, yes):
    """Drops database"""
    if yes or click.confirm('Drop database?'):
        with open(user_dump_path, 'w') as f:
            for s in iterate_user_strings(ctx.obj, True):
                print(s, file=f)
        click.echo('Dumped users to {}'.format(user_dump_path))
        ctx.obj.drop_database()


@manage.group()
def user():
    """Manage users"""


@user.command()
@click.option('-p', '--with-passwords', is_flag=True)
@click.pass_context
def ls(ctx, with_passwords):
    """Lists all users"""
    for s in iterate_user_strings(ctx.obj, with_passwords):
        click.echo(s)


@user.command()
@click.argument('email')
@click.argument('password')
@click.option('-a', '--admin', is_flag=True, help="Add admin role")
@click.option('-s', '--scai', is_flag=True, help="Add SCAI role")
@click.pass_context
def add(ctx, email, password, admin, scai):
    """Creates a new user"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    try:
        u = ds.create_user(email=email, password=password, confirmed_at=datetime.datetime.now())

        if admin:
            ds.add_role_to_user(u, 'admin')

        if scai:
            ds.add_role_to_user(u, 'scai')

        ds.commit()
    except:
        log.exception("Couldn't create user")


@user.command()
@click.argument('email')
@click.pass_context
def rm(ctx, email):
    """Deletes a user"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    u = ds.find_user(email=email)
    ds.delete_user(u)
    ds.commit()


@user.command()
@click.argument('email')
@click.pass_context
def make_admin(ctx, email):
    """Makes a given user an admin"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    try:
        ds.add_role_to_user(email, 'admin')
        ds.commit()
    except:
        log.exception("Couldn't make admin")


@user.command()
@click.argument('email')
@click.argument('role')
@click.pass_context
def add_role(ctx, email, role):
    """Adds a role to a user"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    try:
        ds.add_role_to_user(email, role)
        ds.commit()
    except:
        log.exception("Couldn't add role")


@manage.group()
def role():
    """Manage roles"""


@role.command()
@click.argument('name')
@click.option('-d', '--description')
@click.pass_context
def add(ctx, name, description):
    """Creates a new role"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    try:
        ds.create_role(name=name, description=description)
        ds.commit()
    except:
        log.exception("Couldn't create role")


@role.command()
@click.argument('name')
@click.pass_context
def rm(ctx, name):
    """Deletes a user"""
    ds = SQLAlchemyUserDatastore(ctx.obj, User, Role)
    u = ds.find_role(name)
    if u:
        ds.delete(u)
        ds.commit()


@role.command()
@click.pass_context
def ls(ctx):
    """Lists roles"""
    for r in ctx.obj.session.query(Role).all():
        click.echo('{}\t{}'.format(r.name, r.description))


if __name__ == '__main__':
    main()
