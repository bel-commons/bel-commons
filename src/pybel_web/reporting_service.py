# -*- coding: utf-8 -*-

import logging

from flask import render_template, Blueprint
from werkzeug.local import LocalProxy

from .models import Report
from .utils import get_current_manager

log = logging.getLogger(__name__)

reporting_blueprint = Blueprint('reporting', __name__)
manager = LocalProxy(get_current_manager)


@reporting_blueprint.route('/reporting', methods=['GET'])
def view_reports():
    """Shows the uploading reporting"""
    reports = manager.session.query(Report).order_by(Report.created).all()
    return render_template('reporting.html', reports=reports)


@reporting_blueprint.route('/reporting/user/<username>', methods=['GET'])
def view_individual_report(username):
    """Shows the reports for a given user"""
    reports = manager.session.query(Report).filter_by(Report.username == username).order_by(Report.created).all()
    return render_template('reporting.html', reports=reports)
