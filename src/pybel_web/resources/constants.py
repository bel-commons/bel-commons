import os

dir_path = os.path.dirname(os.path.realpath(__file__))

_bms_base_env_name = 'BMS_BASE'
_omics_dir_env_name = 'BEL_COMMONS_EXAMPLES_OMICS_DATA_DIR'

BMS_BASE = os.environ.get(_bms_base_env_name)
if BMS_BASE is None:
    raise RuntimeError('{} is not set in the environment'.format(_bms_base_env_name))

alzheimer_directory = os.path.join(BMS_BASE, 'aetionomy', 'alzheimers')
parkinsons_directory = os.path.join(BMS_BASE, 'aetionomy', 'parkinsons')
epilepsy_directory = os.path.join(BMS_BASE, 'aetionomy', 'epilepsy')
neurommsig_directory = os.path.join(BMS_BASE, 'aetionomy', 'neurommsig')
selventa_directory = os.path.join(BMS_BASE, 'selventa')
cbn_human = os.path.join(BMS_BASE, 'cbn', 'Human-2.0')
cbn_mouse = os.path.join(BMS_BASE, 'cbn', 'Mouse-2.0')
cbn_rat = os.path.join(BMS_BASE, 'cbn', 'Rat-2.0')

OMICS_DATA_DIR = os.environ.get(_omics_dir_env_name)
if OMICS_DATA_DIR is None:
    raise RuntimeError(
        '{} is not set in the environment. git clone from https://github.com/cthoyt/bel-commons-manuscript'.format(
            _omics_dir_env_name))
