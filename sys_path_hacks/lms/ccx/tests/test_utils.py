from sys_path_hacks.warn import warn_deprecated_import

warn_deprecated_import('lms.djangoapps', 'ccx.tests.test_utils')

from lms.djangoapps.ccx.tests.test_utils import *
