#/*
# * Copyright (c) 2020 Xilinx Inc. All rights reserved.
# *
# * Author:
# *       Appana Durga Kedareswara rao <appana.durga.rao@xilinx.com>
# *
# * SPDX-License-Identifier: BSD-3-Clause
# */
import sys
import types
import os
import re
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

from functools import reduce
from operator import add
sys.path.append(os.path.dirname(__file__))
from baremetalconfig_xlnx import *

def is_compat(node, compat_string_to_test):
    if re.search( "module,baremetaldrvlist_xlnx", compat_string_to_test):
        return xlnx_generate_bm_drvlist
    return ""


# tgt_node: is the baremetal config top level domain node number
# sdt: is the system device-tree
def xlnx_generate_bm_drvlist(tgt_node, sdt, options):
    root_node = sdt.tree[tgt_node]
    root_sub_nodes = root_node.subnodes()
    compatible_list = []
    driver_list = []
    node_list = []
    # Traverse the tree and find the nodes having status=ok property
    # and create a compatible_list from these nodes.
    for node in root_sub_nodes:
        try:
            if node.name == "__symbols__":
                symbol_node = node
            if node.name == "chosen":
                chosen_node = node
            status = node["status"].value
            if "okay" in status:
                compatible_list.append(node["compatible"].value)
                node_list.append(node)
            if node.name == "__symbols__":
                symbol_node = node
        except:
           pass

    tmpdir = os.getcwd()
    src_dir = options['args'][0]
    os.chdir(src_dir) 
    os.chdir("XilinxProcessorIPLib/drivers/")
    cwd = os.getcwd()
    files = os.listdir(cwd)
    depdrv_list = []
    consoledrv_dict = {}
    for name in files:
        os.chdir(cwd)
        if os.path.isdir(name):
            os.chdir(name)
            if os.path.isdir("data"):
                os.chdir("data")
                yamlfile = name + str(".yaml")
                try:
                    # Traverse each driver and find supported compatible list
                    # match it aginst the compatible_list created above, if there
                    # is a match append the driver name to the driver list.
                    with open(yamlfile, 'r') as stream:
                        schema = yaml.safe_load(stream)
                        driver_compatlist = compat_list(schema)
                        for comp in driver_compatlist:
                            for c in compatible_list:
                                match = [x for x in c if comp == x]
                                if match:
                                    consoledrv_dict.update({name:comp})
                                    driver_list.append(name)
                                    try:
                                        if schema['depends']:
                                            depdrv_list.append(schema['depends'])
                                    except:
                                        pass
                except FileNotFoundError:
                    pass

    for depdrv in depdrv_list:
        if isinstance(depdrv, list):
            for dep in depdrv:
                driver_list.append(dep)
        else:
            driver_list.append(depdrv) 
    driver_list = list(dict.fromkeys(driver_list))
    driver_list.sort()
    os.chdir(tmpdir)
    with open('CMakeLists.txt', 'w') as fd:
        fd.write("cmake_minimum_required(VERSION 2.8.9)\n")
        fd.write("include(${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/common.cmake NO_POLICY_SCOPE)\n")
        fd.write("project(xil)\n\n")
        fd.write("enable_language(C)\n\n")
        fd.write("include_directories(${CMAKE_BINARY_DIR}/include)\n")
        tmp_str =  "${CMAKE_CURRENT_SOURCE_DIR}"
        tmp_str = '"{}"'.format(tmp_str)
        fd.write("collector_create (PROJECT_LIB_SOURCES %s)\n" % tmp_str)
        fd.write("collector_create (PROJECT_LIB_HEADERS %s)\n" % tmp_str)
        fd.write("file(COPY ${CMAKE_CURRENT_SOURCE_DIR}/xhw_config.h DESTINATION ${CMAKE_CURRENT_BINARY_DIR}/include)\n\n")
        for driver in driver_list:
            fd.write("add_subdirectory(%s/src)\n" % driver)
        fd.write("add_subdirectory(common/src)\n")
        fd.write("collector_list (_sources PROJECT_LIB_SOURCES)\n")
        fd.write("message( ${_sources})\n")
        fd.write("add_library(xil STATIC ${_sources})\n")
        fd.write("install(TARGETS xil LIBRARY DESTINATION ${CMAKE_SOURCE_DIR}/build ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})\n")
    
    with open('drvlist', 'w') as fd:
        fd.write(';'.join(driver_list))

    prop_dict = Lopper.node_properties_as_dict(sdt.FDT, symbol_node.abs_path)
    ipname_list = []
    for ipname,node in prop_dict.items():
        match = [x for x in node_list if re.search(x.name, node[0])]
        if match:
            ipname_list.append(ipname)

    ipname_list.sort()
    prop_dict = Lopper.node_properties_as_dict(sdt.FDT, chosen_node.abs_path)
    for prop,node in prop_dict.items():
        if prop == "stdout-path":
            serial_node = sdt.FDT.get_alias(node[0].split(':')[0])
            match = [x for x in node_list if re.search(x.name, serial_node)]
            if match:
                list1 = match[0]['compatible'].value
                reg, size = scan_reg_size(match[0],  match[0]['reg'].value, 0)
                console_addr = reg 
                for compat in list1:
                    match = [key for key,x in consoledrv_dict.items() if re.search(x, compat)]
                    if match:
                        console_drvname = match[0]

    gic_enabled = [x for x in driver_list if x == "scugic"]
    print("gic_enabled", gic_enabled)
    with open('xhw_config.h', 'w') as fd:
        fd.write("#ifndef XHW_CONFIG_H_ \n")
        fd.write("#define XHW_CONFIG_H_ \n\n")
        for ipname in ipname_list:
            fd.write("#define XPAR_%s\n" % ipname.upper())
        fd.write("#define XPAR_STDIN_IS_%s\n" % console_drvname.upper())
        fd.write("#define STDIN_BASEADDRESS\t %s\n" % hex(console_addr))
        fd.write("#define STDOUT_BASEADDRESS\t %s\n" % hex(console_addr))
        if gic_enabled:
            fd.write("\n#define XPAR_SCUGIC")
        fd.write("\n#endif \n")

    return driver_list
