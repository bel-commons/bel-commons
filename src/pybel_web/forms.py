# -*- coding: utf-8 -*-

"""A collection of WTForms used through the app"""

from flask_security import RegisterForm
from flask_security.forms import get_form_field_label
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import fields, StringField, SubmitField
from wtforms.fields import BooleanField, RadioField, HiddenField
from wtforms.validators import DataRequired

from pybel_tools.selection.induce_subgraph import (
    SEED_TYPE_INDUCTION,
    SEED_TYPE_PATHS,
    SEED_TYPE_NEIGHBORS,
    SEED_TYPE_DOUBLE_NEIGHBORS,
    SEED_TYPE_UPSTREAM,
    SEED_TYPE_DOWNSTREAM
)


class UploadForm(FlaskForm):
    """Builds an upload form with wtf-forms"""
    file = FileField('A PyBEL gpickle', validators=[
        DataRequired(message="You must provide a PyBEL gpickle file"),
        FileAllowed(['gpickle'], 'Only files with the *.gpickle extension are allowed')
    ])
    public = BooleanField('Make my knowledge assembly be made publicly available', default=True)
    submit = fields.SubmitField('Upload')


class SeedSubgraphForm(FlaskForm):
    """Builds the form for seeding by subgraph"""
    node_list = HiddenField('Nodes')
    seed_method = fields.RadioField(
        'Expansion Method',
        choices=[
            (SEED_TYPE_INDUCTION, 'Induce a subgraph over the given nodes'),
            (SEED_TYPE_NEIGHBORS, 'Induce a subgraph over the given nodes and expand to their first neighbors'),
            (SEED_TYPE_DOUBLE_NEIGHBORS, 'Induce a subgraph over the given nodes and expand to their second neighbors'),
            (SEED_TYPE_PATHS, 'Induce a subgraph over the nodes in all shortest paths between the given nodes'),
            (SEED_TYPE_UPSTREAM, 'Generate an upstream candidate mechanism'),
            (SEED_TYPE_DOWNSTREAM, 'Generate a downstream candidate mechanism'),
        ],
        default=SEED_TYPE_INDUCTION)
    filter_pathologies = BooleanField('Filter pathology nodes', default=False)
    submit_subgraph = fields.SubmitField('Submit Subgraph')


class SeedProvenanceForm(FlaskForm):
    """Builds the form for seeding by author/citation"""
    author_list = HiddenField('Nodes')
    pubmed_list = HiddenField('Nodes')
    filter_pathologies = BooleanField('Filter pathology nodes', default=True)
    submit_provenance = fields.SubmitField('Submit Provenance')


class ParserForm(FlaskForm):
    """Builds an upload form with wtf-forms"""
    file = FileField('My BEL script', validators=[
        DataRequired(),
        FileAllowed(['bel'], 'Only files with the *.bel extension are allowed')
    ])
    suggest_name_corrections = BooleanField('Suggest name corrections')
    suggest_naked_name = BooleanField('My document contains unqualified names - suggest appropriate namespaces')
    allow_nested = BooleanField('My document contains nested statements')
    citation_clearing = BooleanField("My document sometimes has evidences before citations - disable citation clearing")
    save_network = BooleanField('Save my knowledge assembly for later viewing')
    save_edge_store = BooleanField('Save my knowledge assembly and cache in edge store for querying and exploration')
    public = BooleanField('Make my knowledge assembly publicly available', default=True)
    encoding = RadioField(
        'Encoding',
        choices=[
            ('utf-8', 'My document is encoded in UTF-8'),
            ('utf_8_sig', 'My document is encoded in UTF-8 with a BOM (for Windows users who are having problems)')
        ],
        default='utf-8')
    submit = fields.SubmitField('Upload')


class DifferentialGeneExpressionForm(FlaskForm):
    """Builds the form for uploading differential gene expression data"""
    file = FileField('Differential Gene Expression File', validators=[DataRequired()])
    gene_symbol_column = fields.StringField('Gene Symbol Column Name', default='Gene.symbol')
    log_fold_change_column = fields.StringField('Log Fold Change Column Name', default='logFC')
    permutations = fields.IntegerField('Number of Permutations', default=100)
    description = fields.StringField('Description of Data', validators=[DataRequired()])
    separator = RadioField(
        'Separator',
        choices=[
            ('\t', 'My document is a TSV file'),
            (',', 'My document is a CSV file'),
        ],
        default='\t')
    submit = fields.SubmitField('Analyze')


class ExtendedRegisterForm(RegisterForm):
    """Extends the Flask-Security registration form"""
    first_name = StringField('First Name', [DataRequired()])
    last_name = StringField('Last Name', [DataRequired()])
    submit = SubmitField(get_form_field_label('register'))
