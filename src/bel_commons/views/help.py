# -*- coding: utf-8 -*-

"""A blueprint containing help pages for BEL Commons."""

from flask import Blueprint, current_app, redirect, render_template, url_for

from pybel.struct.pipeline.decorators import no_arguments_map

__all__ = [
    'help_blueprint',
]

help_blueprint = Blueprint('help', __name__, url_prefix='/help')


@help_blueprint.route('/')
def index():
    """View the index of all help pages."""
    return redirect(url_for('ui.view_about'))


@help_blueprint.route('/tutorial')
def tutorial():
    """View the BEL Commons tutorial."""
    return render_template(
        'help/tutorial.html',
        blueprints=set(current_app.blueprints),
    )


@help_blueprint.route('/parser')
def parser():
    """View the help page for the parser and validator."""
    return render_template('help/parser.html')


@help_blueprint.route('/query-builder')
def query_builder():
    """View the help page for the Query Builder."""
    function_dict = [
        (fname.replace('_', ' ').title(), f.__doc__.split('\n\n')[0])
        for fname, f in no_arguments_map.items()
        if f.__doc__ is not None
    ]

    return render_template('help/query_builder.html', function_dict=function_dict)


@help_blueprint.route('/download-formats')
def download_formats():
    """View the help page for possible download formats."""
    return render_template('help/download_formats.html')


@help_blueprint.route('/differential-gene-expression')
def dgx():
    """View the help page for getting differential gene expression data from the GEO."""
    return render_template('help/get_geo_dgx.html')


@help_blueprint.route('/heat-diffusion')
def heat_diffusion():
    """View the help page for the heat diffusion workflow."""
    return render_template('help/heat_diffusion.html')
