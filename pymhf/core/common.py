from concurrent.futures import ThreadPoolExecutor
import os
import os.path as op

import pymhf.core._internal as _internal

# TODO: Move somewhere else? Not sure where but this doesn't really fit here...
executor: ThreadPoolExecutor = None  # type: ignore

appdata_data = os.environ.get("APPDATA", op.expanduser("~"))
mod_save_dir = op.join(appdata_data, "pymhf", "MOD_SAVES")

if not op.exists(mod_save_dir):
    os.makedirs(mod_save_dir)
