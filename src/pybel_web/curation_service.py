# -*- coding: utf-8 -*-

import codecs
import logging
import re
import time

from flask import Blueprint, render_template, request, make_response
from flask_security import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from six import StringIO
from wtforms import fields
from wtforms.validators import DataRequired

from pybel.constants import NAMESPACE_DOMAIN_TYPES
from pybel.utils import parse_bel_resource
from pybel_tools.definition_utils import write_namespace
from pybel_tools.document_utils import write_boilerplate
from pybel_tools.recuration.suggestions import get_ols_search, get_ols_suggestion

log = logging.getLogger(__name__)


class BoilerplateForm(FlaskForm):
    """Builds a form for generating BEL script templates"""
    name = fields.StringField('Document Name', validators=[DataRequired()])
    description = fields.StringField('Document Description', validators=[DataRequired()])
    pmids = fields.StringField('PubMed Identifiers, separated by commas')
    entrez_ids = fields.StringField('Entrez Identifiers, separated by commas')
    licenses = fields.RadioField(
        'License',
        choices=[
            ('CC BY 4.0', 'Add the CC BY 4.0 license'),
            ('Other/Proprietary', 'Add an "Other/Proprietary" license')
        ],
        default='CC BY 4.0'
    )
    submit = fields.SubmitField('Generate')


class MergeNamespaceForm(FlaskForm):
    """Builds a form for merging namespace files"""
    file = FileField('BEL Namespace Files', render_kw={'multiple': True}, validators=[
        DataRequired(),
        FileAllowed(['belns'], 'Only files with the *.belns extension are allowed')
    ])
    name = fields.StringField('Name', validators=[DataRequired()])
    keyword = fields.StringField('Keyword', validators=[DataRequired()])
    description = fields.StringField('Description', validators=[DataRequired()])
    species = fields.StringField('Species Taxonomy Identifiers', validators=[DataRequired()], default='9606')
    domain = fields.RadioField('Domain', choices=[(x, x) for x in sorted(NAMESPACE_DOMAIN_TYPES)])
    citation = fields.StringField('Citation Name', validators=[DataRequired()])
    licenses = fields.RadioField(
        'License',
        choices=[
            ('CC BY 4.0', 'Add the CC BY 4.0 license'),
            ('Other/Proprietary', 'Add an "Other/Proprietary" license')
        ],
        default='CC BY 4.0'
    )
    submit = fields.SubmitField('Merge')


class ValidateNamespaceForm(FlaskForm):
    """Builds a form for validating a namespace"""
    file = FileField('BEL Namespace File', validators=[
        DataRequired(),
        FileAllowed(['belns'], 'Only files with the *.belns extension are allowed')
    ])
    search_type = fields.RadioField(
        'Search Type',
        choices=[
            ('search', 'Search'),
            ('suggest', 'Suggest')
        ],
        default='search'
    )
    submit = fields.SubmitField('Validate')


def get_resource_from_request_file(file):
    """Iterates over a file stream and gets a BEL resource

    Use like:

    >>> get_resource_from_request_file(form.file.data.stream)

    """
    return parse_bel_resource(codecs.iterdecode(file, 'utf-8'))


curation_blueprint = Blueprint('curation', __name__)


@curation_blueprint.route('/curation/bel/template', methods=['GET', 'POST'])
@login_required
def get_boilerplate():
    """Serves the form for building a template BEL script"""
    form = BoilerplateForm()

    if not form.validate_on_submit():
        return render_template('boilerplate.html', form=form)

    si = StringIO()

    pmids = [int(x.strip()) for x in form.pmids.data.split(',') if x]
    entrez_ids = [int(x.strip()) for x in form.entrez_ids.data.split(',') if x]

    write_boilerplate(
        document_name=form.name.data,
        contact=current_user.email,
        description=form.description.data,
        authors=str(current_user),
        licenses=form.licenses.data,
        version='1.0.0',
        pmids=pmids,
        entrez_ids=entrez_ids,
        file=si
    )

    identifier = re.sub(r"\s+", '_', form.name.data.lower())

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}.bel".format(identifier)
    output.headers["Content-type"] = "text/plain"
    return output


@curation_blueprint.route('/curation/namespace/merge', methods=['GET', 'POST'])
@login_required
def merge_namespaces():
    """Serves the page for merging bel namespaces"""
    form = MergeNamespaceForm()

    if not form.validate_on_submit():
        return render_template('merge_namespaces.html', form=form)

    log.warning(form.file)

    files = request.files.getlist("file")

    names = set()

    for file in files:
        log.warning('file: %s', file)
        resource = parse_bel_resource(codecs.iterdecode(file, 'utf-8'))
        names |= set(resource['Values'])

    si = StringIO()

    write_namespace(
        namespace_name=form.name.data,
        namespace_keyword=form.keyword.data,
        namespace_species=form.species.data,
        namespace_description=form.description.data,
        author_name=current_user.name,
        author_contact=current_user.email,
        citation_name=form.citation.data,
        citation_description='This namespace was created by the PyBEL Web namespace merge service',
        namespace_domain=form.domain.data,
        author_copyright=form.licenses.data,
        values=names,
        cacheable=False,
        file=si
    )

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename={}.belns".format(form.keyword.data)
    output.headers["Content-type"] = "text/plain"
    return output


@curation_blueprint.route('/curation/namespace/validate', methods=['GET', 'POST'])
def validate_namespace():
    """Provides suggestions for namespace curation"""
    form = ValidateNamespaceForm()

    if not form.validate_on_submit():
        return render_template(
            'generic_form.html',
            form=form,
            page_header="Validate Namespace",
            page_title='Validate Namespace'
        )

    resource = parse_bel_resource(codecs.iterdecode(form.file.data.stream, 'utf-8'))

    search_fn = get_ols_search if form.search_type.data == 'search' else get_ols_suggestion
    t = time.time()
    results = {}
    for name in sorted(resource['Values']):
        response = search_fn(name)
        results[name] = response['response']['docs']

    return render_template(
        'namespace_validation.html',
        data=results,
        timer=round(time.time() - t),
        namespace_name=resource['Namespace']['NameString']
    )
