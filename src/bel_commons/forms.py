# -*- coding: utf-8 -*-

"""Forms encoded in WTForms for BEL Commons."""

import logging
from typing import Mapping

from celery.task import Task
from flask import flash
from flask_security import RegisterForm, current_user
from flask_security.forms import get_form_field_label
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms.fields import BooleanField, HiddenField, IntegerField, RadioField, StringField, SubmitField
from wtforms.validators import DataRequired

from pybel.struct.query.constants import (
    SEED_TYPE_DOUBLE_NEIGHBORS, SEED_TYPE_DOWNSTREAM, SEED_TYPE_INDUCTION, SEED_TYPE_NEIGHBORS, SEED_TYPE_PATHS,
    SEED_TYPE_UPSTREAM,
)
from .celery_worker import parse

logger = logging.getLogger(__name__)


class SeedSubgraphForm(FlaskForm):
    """Builds the form for seeding by sub-graph."""

    node_list = HiddenField('Nodes')
    seed_method = RadioField(
        'Expansion Method',
        choices=[
            (SEED_TYPE_NEIGHBORS, 'Induce a subgraph over the given nodes and expand to their first neighbors'),
            (SEED_TYPE_DOUBLE_NEIGHBORS, 'Induce a subgraph over the given nodes and expand to their second neighbors'),
            (SEED_TYPE_PATHS, 'Induce a subgraph over the nodes in all shortest paths between the given nodes'),
            (SEED_TYPE_UPSTREAM, 'Induce over upstream causal neighbors (2 layers)'),
            (SEED_TYPE_DOWNSTREAM, 'Induce over downstream causal neighbors (2 layers)'),
            (SEED_TYPE_INDUCTION, 'Only induce a subgraph over the given nodes'),
        ],
        default=SEED_TYPE_NEIGHBORS,
    )
    filter_pathologies = BooleanField('Filter pathology nodes', default=False)
    submit_subgraph = SubmitField('Submit Subgraph')


class SeedProvenanceForm(FlaskForm):
    """Builds the form for seeding by author/citation."""

    author_list = HiddenField('Nodes')
    pubmed_list = HiddenField('Nodes')
    filter_pathologies = BooleanField('Filter pathology nodes', default=True)
    submit_provenance = SubmitField('Submit Provenance')


class BaseParserForm(FlaskForm):
    """A base parser form."""

    file = FileField('My BEL script (version 1.0 or 2.0+)', validators=[
        DataRequired(),
        FileAllowed(['bel'], 'Only files with the *.bel extension are allowed')
    ])
    submit = SubmitField('Upload')

    def get_parse_kwargs(self) -> Mapping[str, bool]:
        """Get kwargs to send to the PyBEL parser."""
        raise NotImplementedError

    def send_parse_task(self) -> Task:
        """Send the contents of the file to celery."""
        name = self.file.data.filename
        contents = self.file.data.stream.read().decode('utf-8')

        try:
            current_user_id = current_user.id
        except AttributeError:  # if it's not availble
            current_user_id = None

        task = parse.delay(
            name,
            contents,
            self.get_parse_kwargs(),
            current_user_id,
        )
        message = f'Queued parsing task {task.id} on {name}'
        logger.info(message)
        flash(message)
        return task


class ParserForm(BaseParserForm):
    """Builds an upload form with wtf-forms."""

    disable_citation_clearing = BooleanField(
        'My document sometimes has evidences before citations - disable <a href="h'
        'ttp://pybel.readthedocs.io/en/latest/io.html#citation-clearing">citation '
        'clearing</a>'
    )
    public = BooleanField('Make my knowledge assembly publicly available', default=True)
    infer_origin = BooleanField('Enrich protein nodes with their corresponding RNA and gene nodes', default=False)

    def get_parse_kwargs(self):  # noqa: D102
        return dict(
            public=self.public.data,
            infer_origin=self.infer_origin.data,
            citation_clearing=not self.disable_citation_clearing.data,
        )


class DifferentialGeneExpressionForm(FlaskForm):
    """Builds the form for uploading differential gene expression data."""

    file = FileField('Differential Gene Expression File', validators=[DataRequired()])
    gene_symbol_column = StringField('Gene Symbol Column Name', default='Gene.symbol')
    log_fold_change_column = StringField('Log Fold Change Column Name', default='logFC')
    permutations = IntegerField('Number of Permutations', default=100)
    description = StringField('Description of Data', validators=[DataRequired()])
    omics_public = BooleanField('Make my experimental source data publicly available', default=False)
    results_public = BooleanField('Make my experimental results publicly available', default=False)
    separator = RadioField(
        'Separator',
        choices=[
            ('\t', 'My document is a TSV file'),
            (',', 'My document is a CSV file'),
        ],
        default='\t',
    )
    submit = SubmitField('Analyze')


class ExtendedRegisterForm(RegisterForm):
    """Extends the Flask-Security registration form."""

    name = StringField('Name', [DataRequired()])
    submit = SubmitField(get_form_field_label('register'))
