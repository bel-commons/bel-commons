# -*- coding: utf-8 -*-

import logging

from flask import redirect, url_for, request
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView as ModelViewBase
from flask_security import current_user

from pybel.manager.models import Network, Namespace, Annotation
from .application import get_manager
from .models import Report, Experiment, Role, User, Query, Assembly

log = logging.getLogger(__name__)


class ModelView(ModelViewBase):
    """Adds plugin for Flask-Security to Flask-Admin model views"""

    def is_accessible(self):
        """Checks the current user is an admin"""
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        """redirect to login page if user doesn't have access"""
        return redirect(url_for('login', next=request.url))


class NetworkView(ModelView):
    """Special view for PyBEL Web Networks"""
    column_exclude_list = ['blob', ]


class UserView(ModelView):
    """Special view for PyBEL Web Users"""
    column_exclude_list = ['password', ]


def build_admin_service(app):
    """Adds Flask-Admin database front-end
    
    :param flask.Flask app: A PyBEL web app
    :rtype flask_admin.Admin
    """
    manager = get_manager(app)
    admin = Admin(app, template_mode='bootstrap3')
    admin.add_view(UserView(User, manager.session))
    admin.add_view(ModelView(Role, manager.session))
    admin.add_view(ModelView(Namespace, manager.session))
    admin.add_view(ModelView(Annotation, manager.session))
    admin.add_view(NetworkView(Network, manager.session))
    admin.add_view(ModelView(Report, manager.session))
    admin.add_view(ModelView(Experiment, manager.session))
    admin.add_view(ModelView(Query, manager.session))
    admin.add_view(ModelView(Assembly, manager.session))

    log.info('Added admin service for %s', app)

    return admin
