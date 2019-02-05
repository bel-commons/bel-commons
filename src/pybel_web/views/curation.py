# -*- coding: utf-8 -*-

import codecs
import logging
import re
from io import StringIO

import time
from bel_resources import parse_bel_resource, write_namespace
from flask import Blueprint, make_response, render_template, request
from flask_security import current_user, login_required, roles_required
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from ols_client import OlsClient
from wtforms import fields
from wtforms.validators import DataRequired

from pybel.constants import NAMESPACE_DOMAIN_TYPES
from pybel.utils import get_version as get_pybel_version
from pybel_tools.document_utils import write_boilerplate

log = logging.getLogger(__name__)

curation_blueprint = Blueprint('curation', __name__, url_prefix='/curation')


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


class ValidateResourceForm(FlaskForm):
    """Builds a form for validating a namespace"""
    file = FileField('BEL Namespace or Annotation', validators=[
        DataRequired(),
        FileAllowed(['belns', 'belanno'], 'Only files with the *.belns or *.belanno extension are allowed')
    ])
    submit = fields.SubmitField('Validate')

    def parse_bel_resource(self):
        return parse_bel_resource(codecs.iterdecode(self.file.data.stream, 'utf-8'))


@curation_blueprint.route('/bel/template', methods=['GET', 'POST'])
@login_required
def get_boilerplate():
    """Serves the form for building a template BEL script"""
    form = BoilerplateForm()

    if not form.validate_on_submit():
        return render_template('curation/boilerplate.html', form=form)

    si = StringIO()

    pmids = [int(x.strip()) for x in form.pmids.data.split(',') if x]
    entrez_ids = [int(x.strip()) for x in form.entrez_ids.data.split(',') if x]

    write_boilerplate(
        name=form.name.data,
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


@curation_blueprint.route('/namespace/merge', methods=['GET', 'POST'])
@login_required
def merge_namespaces():
    """Serves the page for merging bel namespaces"""
    form = MergeNamespaceForm()

    if not form.validate_on_submit():
        return render_template('curation/merge_namespaces.html', form=form)

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
        citation_description='This merged namespace was created by the PyBEL v{}'.format(get_pybel_version()),
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


@curation_blueprint.route('/namespace/validate', methods=['GET', 'POST'])
def validate_resource():
    """Provides suggestions for namespace and annotation curation"""
    form = ValidateResourceForm()

    if not form.validate_on_submit():
        return render_template(
            'generic_form.html',
            form=form,
            page_header="Validate Namespace",
            page_title='Validate Namespace',
            paragraphs=[
                """This service wraps the EBI OLS's suggestion service in order to generate a table for mapping
                custom BEL namespaces to standard ontologies."""
            ]
        )

    resource = form.parse_bel_resource()

    ols = OlsClient()

    t = time.time()

    results = {}
    missing_suggestion = set()

    for name in sorted(resource['Values']):
        response = ols.suggest(name.strip().strip('"').strip("'"))

        if response['response']['numFound'] == 0:
            missing_suggestion.add(name)
        else:
            results[name] = response

    return render_template(
        'curation/ols_suggestion.html',
        data=results,
        missing_suggestion=missing_suggestion,
        timer=round(time.time() - t),
        namespace_name=resource['Namespace']['NameString']
    )


@curation_blueprint.route('/interface')
@roles_required('admin')
def view_curation_interface():
    """View the curation interface prototype"""
    return render_template('curation/curate.html')
