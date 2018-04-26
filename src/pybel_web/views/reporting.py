# -*- coding: utf-8 -*-

"""This module helps make summary pages"""

import datetime
import logging

from flask import Blueprint, render_template
from flask_security import roles_required

from ..models import Report
from ..proxies import manager

log = logging.getLogger(__name__)

reporting_blueprint = Blueprint('reporting', __name__, url_prefix='/reporting')


@reporting_blueprint.route('/')
@roles_required('admin')
def view_report():
    """This view gives an overview of the user actions in the last 7 days"""
    interval = datetime.datetime.now() - datetime.timedelta(days=7)

    reports = manager.session.query(Report).filter(Report.created > interval)

    date_report = {
        report.created.strftime('%Y%m%d'): report
        for report in reports
    }

    return render_template('reporting/report.html', date_report=date_report)


@reporting_blueprint.route('/network', methods=['GET'])
@roles_required('admin')
def view_networks():
    """Shows the uploading reporting"""
    return render_template('reporting/networks.html',
                           reports=manager.session.query(Report).order_by(Report.created).all())
