import os
import os.path as op
from concurrent.futures import ThreadPoolExecutor
import pymhf.core.utils as utils

# TODO: Move somewhere else? Not sure where but this doesn't really fit here...
executor: ThreadPoolExecutor = None  # type: ignore

mod_save_dir = op.join(utils.get_cfg_dir(), "MOD_SAVES")
if not op.exists(mod_save_dir):
    os.makedirs(mod_save_dir)
