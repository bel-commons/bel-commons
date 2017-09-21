# -*- coding: utf-8 -*-

import logging
import time

import git
from flask import current_app, Blueprint, flash, redirect, url_for, jsonify
from flask_security import roles_required

from pybel_tools.ioutils import get_paths_recursive, upload_recursive
from .constants import *
from .utils import next_or_jsonify, manager

log = logging.getLogger(__name__)

bms_blueprint = Blueprint('bms', __name__)


@bms_blueprint.route('/admin/bms/meta/git-update')
def git_pull():
    """Updates the Biological Model Store git repository"""
    git_dir = os.environ['BMS_BASE']
    g = git.cmd.Git(git_dir)
    res = g.pull()

    return next_or_jsonify(res)


@bms_blueprint.route('/admin/bms/parse/all')
@roles_required('admin')
def ensure_bms():
    """Parses and stores the entire Biological Model Store repository"""
    task = current_app.celery.send_task('parse-bms')
    return next_or_jsonify('Queued task to parse the BMS: {}'.format(task))


@bms_blueprint.route('/admin/bms/list/all')
@roles_required('admin')
def list_bms_pickles():
    """Lists the pre-parsed gpickles in the Biological Model Store repository"""
    return jsonify(list(get_paths_recursive(os.environ[BMS_BASE], extension='.gpickle')))


@bms_blueprint.route('/admin/bms/upload/all')
@roles_required('admin')
def upload_bms():
    """Synchronously uploads the gpickles in the Biological Model Store repository"""
    t = time.time()
    upload_recursive(os.path.join(os.environ[BMS_BASE]), connection=manager)
    flash('Uploaded the BMS folder in {:.2f} seconds'.format(time.time() - t))
    return redirect(url_for('home'))


@bms_blueprint.route('/admin/bms/parse/aetionomy')
@roles_required('admin')
def ensure_aetionomy():
    """Parses and stores the AETIONOMY resources from the Biological Model Store repository"""
    task = current_app.celery.send_task('parse-aetionomy')
    return next_or_jsonify('Queued task to parse the AETIONOMY folder: {}'.format(task))


@bms_blueprint.route('/admin/bms/upload/aetionomy')
@roles_required('admin')
def upload_aetionomy():
    """Uploads the gpickles in the AETIONOMY section of the Biological Model Store repository"""
    t = time.time()
    upload_recursive(os.path.join(os.environ[BMS_BASE], 'aetionomy'), connection=manager)
    flash('Uploaded the AETIONOMY folder in {:.2f} seconds'.format(time.time() - t))
    return redirect(url_for('home'))


@bms_blueprint.route('/admin/bms/parse/selventa')
@roles_required('admin')
def ensure_selventa():
    """Parses and stores the Selventa resources from the Biological Model Store repository"""
    task = current_app.celery.send_task('parse-selventa')
    return next_or_jsonify('Queued task to parse the Selventa folder: {}'.format(task))


@bms_blueprint.route('/admin/bms/parse/ptsd')
@roles_required('admin')
def ensure_ptsd():
    """Parses and stores the PTSD resources from the Biological Model Store repository"""
    task = current_app.celery.send_task('parse-ptsd')
    return next_or_jsonify('Queued task to parse the PTSD folder: {}'.format(task))


@bms_blueprint.route('/admin/bms/parse/tbi')
@roles_required('admin')
def ensure_tbi():
    """Parses and stores the TBI resources from the Biological Model Store repository"""
    task = current_app.celery.send_task('parse-tbi')
    return next_or_jsonify('Queued task to parse the TBI folder: {}'.format(task))


@bms_blueprint.route('/admin/bms/parse/bel4imocede')
@roles_required('admin')
def ensure_bel4imocede():
    """Parses and stores the BEL4IMOCEDE resources from the Biological Model Store repository"""
    task = current_app.celery.send_task('parse-bel4imocede')
    return next_or_jsonify('Queued task to parse the BEL4IMOCEDE folder: {}'.format(task))
