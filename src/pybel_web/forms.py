# -*- coding: utf-8 -*-

"""Forms encoded in WTForms for PyBEL Web."""

from flask_security import RegisterForm
from flask_security.forms import get_form_field_label
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms.fields import BooleanField, HiddenField, IntegerField, RadioField, StringField, SubmitField
from wtforms.validators import DataRequired

from pybel_tools.selection.induce_subgraph import (
    SEED_TYPE_DOUBLE_NEIGHBORS, SEED_TYPE_DOWNSTREAM, SEED_TYPE_INDUCTION,
    SEED_TYPE_NEIGHBORS, SEED_TYPE_PATHS, SEED_TYPE_UPSTREAM,
)


class SeedSubgraphForm(FlaskForm):
    """Builds the form for seeding by subgraph"""
    node_list = HiddenField('Nodes')
    seed_method = RadioField(
        'Expansion Method',
        choices=[
            (SEED_TYPE_NEIGHBORS, 'Induce a subgraph over the given nodes and expand to their first neighbors'),
            (SEED_TYPE_DOUBLE_NEIGHBORS, 'Induce a subgraph over the given nodes and expand to their second neighbors'),
            (SEED_TYPE_PATHS, 'Induce a subgraph over the nodes in all shortest paths between the given nodes'),
            (SEED_TYPE_UPSTREAM, 'Generate an upstream candidate mechanism'),
            (SEED_TYPE_DOWNSTREAM, 'Generate a downstream candidate mechanism'),
            (SEED_TYPE_INDUCTION, 'Only induce a subgraph over the given nodes'),
        ],
        default=SEED_TYPE_NEIGHBORS)
    filter_pathologies = BooleanField('Filter pathology nodes', default=False)
    submit_subgraph = SubmitField('Submit Subgraph')


class SeedProvenanceForm(FlaskForm):
    """Builds the form for seeding by author/citation"""
    author_list = HiddenField('Nodes')
    pubmed_list = HiddenField('Nodes')
    filter_pathologies = BooleanField('Filter pathology nodes', default=True)
    submit_provenance = SubmitField('Submit Provenance')


class ParserForm(FlaskForm):
    """Builds an upload form with wtf-forms"""
    file = FileField('My BEL script', validators=[
        DataRequired(),
        FileAllowed(['bel'], 'Only files with the *.bel extension are allowed')
    ])
    # suggest_name_corrections = BooleanField('Suggest name corrections')
    # suggest_naked_name = BooleanField('My document contains unqualified names - suggest appropriate namespaces')
    allow_nested = BooleanField(
        'My document contains <a href="http://pybel.readthedocs.io/en/latest/io.html#allow-nested">nested statements</a>')
    disable_citation_clearing = BooleanField(
        'My document sometimes has evidences before citations - disable <a href="http://pybel.readthedocs.io/en/latest/io.html#citation-clearing">citation clearing</a>')
    feedback = BooleanField('Just email me a summary of my network and error report', default=False)
    public = BooleanField('Make my knowledge assembly publicly available', default=True)
    infer_origin = BooleanField(
        'Infer the <a href="https://en.wikipedia.org/wiki/Central_dogma_of_molecular_biology">central dogma</a>',
        default=False)
    encoding = RadioField(
        'Encoding',
        choices=[
            ('utf-8', 'My document is encoded in UTF-8'),
            ('utf_8_sig', 'My document is encoded in UTF-8 with a BOM (for Windows users who are having problems)')
        ],
        default='utf-8')
    submit = SubmitField('Upload')


class DifferentialGeneExpressionForm(FlaskForm):
    """Builds the form for uploading differential gene expression data"""
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
        default='\t')
    submit = SubmitField('Analyze')


class ExtendedRegisterForm(RegisterForm):
    """Extends the Flask-Security registration form"""
    name = StringField('Name', [DataRequired()])
    submit = SubmitField(get_form_field_label('register'))
