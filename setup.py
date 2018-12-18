# -*- coding: utf-8 -*-

"""Setup for PyBEL Web."""

import codecs
import os
import re

import setuptools

#################################################################

PACKAGES = setuptools.find_packages(where='src')
META_PATH = os.path.join('src', 'pybel_web', '__init__.py')
KEYWORDS = ['Biological Expression Language', 'BEL', 'Systems Biology', 'Networks Biology']
CLASSIFIERS = [
    'Development Status :: 1 - Planning',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: Apache Software License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Topic :: Scientific/Engineering :: Bio-Informatics',
]
INSTALL_REQUIRES = [
    'ols_client>=0.0.8',
    'pybel>=0.12.0',
    'pybel-tools>=0.7.0',
    'networkx>=2.1',
    'requests',
    'sqlalchemy',
    'flask',
    'flask-bootstrap==3.3.7.1',
    'flask-wtf',
    'flask-security==3.0.0',
    'flask-admin',
    'flask-cors',
    'flask-sqlalchemy==2.2',
    'werkzeug',
    'flasgger',
    'click',
    'pandas',
    'celery',
    'raven',
    'scikit-learn',
    'numpy',
    'bio2bel',
    'tqdm',
]
EXTRAS_REQUIRE = {
    'bio2bel': [
        'bio2bel_hgnc',
        'bio2bel_chebi',
        'bio2bel_mirtarbase',
        'bio2bel_entrez',
        'bio2bel_expasy',
        'bio2bel_interpro',
        'bio2bel_go',
    ],
    'cx': [
        'pybel_cx>=0.1.1',
    ],
    'postgres': [
        'psycopg2-binary',
    ]
}
TESTS_REQUIRE = []
ENTRY_POINTS = {
    'console_scripts': [
        'pybel-web = pybel_web.cli:main',
    ]
}

#################################################################

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    """Build an absolute path from *parts* and return the contents of the resulting file. Assume UTF-8 encoding."""
    with codecs.open(os.path.join(HERE, *parts), 'rb', 'utf-8') as f:
        return f.read()


META_FILE = read(META_PATH)


def find_meta(meta):
    """Extract __*meta*__ from META_FILE."""
    meta_match = re.search(
        r'^__{meta}__ = ["\']([^"\']*)["\']'.format(meta=meta),
        META_FILE, re.M
    )
    if meta_match:
        return meta_match.group(1)
    raise RuntimeError('Unable to find __{meta}__ string'.format(meta=meta))


def get_long_description():
    """Get the long_description from the README.rst file. Assume UTF-8 encoding."""
    with codecs.open(os.path.join(HERE, 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()
    return long_description


if __name__ == '__main__':
    setuptools.setup(
        name=find_meta('title'),
        version=find_meta('version'),
        description=find_meta('description'),
        long_description=get_long_description(),
        url=find_meta('url'),
        author=find_meta('author'),
        author_email=find_meta('email'),
        maintainer=find_meta('author'),
        license=find_meta('license'),
        classifiers=CLASSIFIERS,
        keywords=KEYWORDS,
        packages=PACKAGES,
        package_dir={'': 'src'},
        include_package_data=True,
        install_requires=INSTALL_REQUIRES,
        extras_require=EXTRAS_REQUIRE,
        tests_require=TESTS_REQUIRE,
        entry_points=ENTRY_POINTS,
        zip_safe=False,
    )
