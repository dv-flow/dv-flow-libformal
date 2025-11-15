#****************************************************************************
#* __ext__.py (skeleton)
#****************************************************************************
import os

def dvfm_packages():
    formal_dir = os.path.dirname(os.path.abspath(__file__))
    return {
        'formal': os.path.join(formal_dir, "flow.dv"),
        'formal.sby': os.path.join(formal_dir, "flow_sby.dv"),
    }
