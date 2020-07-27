#/*
# * Copyright (c) 2020 Xilinx Inc. All rights reserved.
# *
# * Author:
# *       Appana Durga Kedareswara rao <appana.durga.rao@xilinx.com>
# *
# * SPDX-License-Identifier: BSD-3-Clause
# */

import struct
import sys
import types
import unittest
import os
import getopt
import re
import subprocess
import shutil
from pathlib import Path
from pathlib import PurePath
from io import StringIO
import contextlib
import importlib
from lopper import Lopper
from lopper import LopperFmt
import lopper
from lopper_tree import *
from re import *
import yaml

sys.path.append(os.path.dirname(__file__))
from baremetalconfig_xlnx import *
from grep import *

def is_compat( node, compat_string_to_test ):
    if re.search( "module,baremetal_bspconfig_xlnx", compat_string_to_test):
        return xlnx_generate_bm_bspconfig
    return ""

# tgt_node: is the baremetal config top level domain node number
# sdt: is the system device-tree
# options: baremetal application source path
def xlnx_generate_bm_bspconfig(tgt_node, sdt, options):
    root_node = sdt.tree[tgt_node]
    root_sub_nodes = root_node.subnodes()
    mem_nodes = []
    #Maintain a static memory IP list this is needed inorder to capture proper ip name in the xmem_config.h file
    xlnx_memipname = {"axi_bram": 0, "ps7_ddr": 0, "psu_ddr": 0, "psv_ddr": 0, "mig": 0, "lmb_bram": 0, "axi_noc": 0, "psu_ocm": 0,  "psv_ocm": 0, "ddr4": 0}
    for node in root_sub_nodes:
        try:
            device_type = node["device_type"].value
            if "memory" in device_type:
                mem_nodes.append(node)
        except:
           pass
   
    mem_ranges = {}
    for node in mem_nodes:
        na = node.parent["#address-cells"].value[0]
        ns = node.parent["#size-cells"].value[0]
        val = node['reg'].value
        total_nodes = int(len(val)/(na+ns))
        name_list = [name.replace("_", "-") for name in list(xlnx_memipname.keys())]
        try:
            compat = node['compatible'].value[0]
            match = [mem for mem in name_list if mem in compat]
            for i in range(total_nodes):
                reg, size = scan_reg_size(node, val, i)
                key = match[0].replace("-", "_")
                linker_secname = key + str("_") + str(xlnx_memipname[key])
                mem_ranges.update({linker_secname: [reg, size]})
                xlnx_memipname[key] += 1
        except KeyError:
            pass
   
    with open('xmem_config.h', 'w') as fd:
        fd.write("#ifndef XMEM_CONFIG_H_\n")
        fd.write("#define XMEM_CONFIG_H_\n")
        for key, value in sorted(mem_ranges.items(), key=lambda e: e[1][1], reverse=True):
            start,size = value[0], value[1]
            fd.write("\n#define XPAR_%s_BASEADDRESS %s" % (key.upper(), hex(start)))
            fd.write("\n#define XPAR_%s_HIGHADDRESS %s" % (key.upper(), hex(start + size)))
        fd.write("\n\n#endif\n")

    # Machine to config struct mapping
    cpu_dict = {'cortexa53-zynqmp': 'arm,cortex-a53', 'cortexa72-versal':'arm,cortex-a72', 'cortexr5-zynqmp': 'arm,cortex-r5', 'cortexa9-zynq': 'arm,cortex-a9',
                'microblaze-pmu': 'pmu-microblaze', 'microblaze-plm': 'pmc-microblaze', 'microblaze-psm': 'psm-microblaze'}
    nodes = sdt.tree.nodes('/cpu.*')
    machine = options['args'][0]
    match_cpunodes = []
    match = cpu_dict[machine]
    for node in nodes:
        try:
            compat = node['compatible'].value[0]
            match = cpu_dict[machine]
            if compat == match:
                match_cpunodes.append(node)
        except KeyError:
            pass

    # Get the yaml file (open each data filder yaml file and find compat match)
    tmpdir = os.getcwd()
    os.chdir(options['args'][1])
    os.chdir("../data")
    cwd = os.getcwd()
    files = os.listdir(cwd)
    for name in files:
        os.chdir(cwd)
        if os.path.isdir(name):
            os.chdir(name)
            yamlfile = name + str(".yaml")
            with open(yamlfile) as stream:
                schema = yaml.safe_load(stream)
                compatlist = compat_list(schema)
                prop_list = schema['required']
                match = [compat for compat in compatlist if compat == cpu_dict[machine]]
                if match:
                   config_struct = schema['config'][0] 
                   outfile = tmpdir + str("/") + str("x") + name.lower() + str("_g.c")
                   with open(outfile, 'w') as fd:
                       fd.write('#include "x%s.h"\n' % name.lower())
                       fd.write('\n%s %s __attribute__ ((section (".drvcfg_sec"))) = {\n' % (config_struct, config_struct + str("Table[]")))
                       for index,prop in enumerate(prop_list):
                           if index == 0:
                               fd.write("\t{")
                           try:
                               fd.write("\n\t\t%s" % hex(match_cpunodes[0][prop].value[0]))
                           except:
                               fd.write("\n\t\t 0")
                           if prop == prop_list[-1]:
                               fd.write("  /* %s */" % prop) 
                               fd.write("\n\t}")
                           else:
                               fd.write(",")
                               fd.write("  /* %s */" % prop) 
                       fd.write("\n};")
    os.chdir(tmpdir)
    
    return True
