#!/usr/bin/env python3

import argparse
import os
import sys
import subprocess
import re
import yaml

import curses
from curses import wrapper
import kconfiglib
from kconfiglib import EQUAL, AND, OR, UNEQUAL, STRING, HEX, INT, LESS_EQUAL, expr_value, NOT, expr_str, Symbol, STR_TO_TRI

L_RED = 1
L_GREEN = 2
L_BLUE = 3
L_WHITE = 4
L_CYAN = 5
L_YELLOW = 6
L_TGT = 7
L_INPUT = 8

configdir = os.path.expandvars("$HOME/.Konfig")
configdir = os.path.expandvars(os.getcwd())

try:
    configfile = open("%s/configs.yaml" % configdir)
    configs = yaml.safe_load(configfile)
except IOError:
    configs = {}

if not "base" in configs:
    print("ERROR: need base in %s/configs.yaml" % configdir)
    sys.exit(0)
if not "sources" in configs["base"]:
    print("ERROR: need base/sources in %s/configs.yaml" % configdir)
    sys.exit(0)

parser = argparse.ArgumentParser()
parser.add_argument("--source", "-s", help="sourcename", type=str, default="default")
parser.add_argument("--arch", "-a", help="arch", type=str, default=None)
parser.add_argument("--defconfig", "-D", help="defconfig", type=str, default=None)
parser.add_argument("--quiet", "-q", help="Quiet, do not print build log", action="store_true")
parser.add_argument("--debug", "-d", help="Quiet, do not print build log", action="store_true")
args = parser.parse_args()

if not args.source in configs["base"]["sources"]:
    print("ERROR: did not find %s in base/sources in %s/configs.yaml" % (args.source, configdir))
    sys.exit(0)
if not "path" in configs["base"]["sources"][args.source]:
    print("ERROR: did not find path in base/sources/%s in %s/configs.yaml" % (args.source, configdir))
    sys.exit(0)

sourcedir = configs["base"]["sources"][args.source]["path"]
os.chdir(sourcedir)

os.environ["srctree"] = sourcedir
if args.arch:
    os.environ["ARCH"] = args.arch
    os.environ["SRCARCH"] = args.arch
os.environ["RUSTC"] = 'rustc'
os.environ["CC"] = 'gcc'
os.environ["LD"] = 'ld'
os.environ["HOSTCC"] = 'gcc'
os.environ["HOSTCXX"] = 'g++'
os.environ["KERNELVERSION"] = "5.12.0"
ret = subprocess.check_output("make kernelversion", shell=True)
os.environ["KERNELVERSION"] = ret.decode("UTF8")

def my_sc_expr_str(sc):
    """
    Standard symbol/choice printing function. Uses plain Kconfig syntax, and
    displays choices as <choice> (or <choice NAME>, for named choices).

    See expr_str().
    """
    if sc.__class__ is Symbol:
        if sc.is_constant and sc.name not in STR_TO_TRI:
            return '"{}"'.format(escape(sc.name + "xx"))
        return sc.name + ":" + sc.str_value

    return "<choice {}>".format(sc.name) if sc.name else "<choice>"

# THIS IS MADNESS
def dprint(x):
    first = False
    second = False
    s1 = x[1]
    if type(x[1]) == tuple:
        st1 = dprint(x[1])
        if st1 != "":
            first = True
    if type(x[1]) == kconfiglib.Symbol:
        s = x[1]
        if args.debug:
            print("selected by %s %s" % (s.name, s.str_value))
        if s.str_value != 'n':
            first = True
            st1 = "%s:%s" % (s.name, s.str_value)
        if s.str_value == s.name:
            first = True
            st1 = "!%s" % s.name
        if x[0] == AND and not first:
            return ""
        #print("ST1: %s" % st1)
    if len(x) == 2:
        if first:
            return st1
        return ""
    s2 = x[2]
    if type(x[2]) == kconfiglib.Symbol:
        s = x[2]
        if args.debug:
            print("2 selected by %s %s" % (s.name, s.str_value))
        if s.str_value != 'n':
            second = True
            st2 = "%s:%s" % (s.name, s.str_value)
        if s.str_value == s.name:
            second = True
            st2 = "!%s" % s.name
    if type(x[2]) == tuple:
        st2 = dprint(x[2])
        if st2 != "":
            second = True
    if x[0] == AND:
        if not second:
            return ""
        fs = st1 + " AND " + st2
        return fs
    elif x[0] == OR:
        if not first and not second:
            return ""
        if not first and second:
            return st2
        if first and not second:
            return st1
        fs = st1 + " OR " + st2
        return fs
    elif x[0] == EQUAL:
        if s1.str_value == s2.str_value:
            return "%s = %s" % (s1.name, s2.name)
        return ""
    elif x[0] == UNEQUAL:
        if s1.str_value != s2.str_value:
            return "%s = %s" % (s1.name, s2.name)
        return ""
    elif x[0] == LESS_EQUAL:
        b = expr_value(x)
        if b == 2:
            fs = "%s:%s <= %s" % (s1.name, s1.str_value, s2.str_value)
        else:
            fs = "%s:%s > %s" % (s1.name, s1.str_value, s2.str_value)
        return fs
    else:
        print("UNKNOWN %d" % x[0])
        if args.debug:
            sys.exit(0)
    return "ERROR"

def prdep(sym):
    if not sym.rev_dep:
        return ""
    if type(sym.rev_dep) == kconfiglib.Symbol:
        if sym.rev_dep.name == "n":
            return ""
        return "SELECTED by %s:%s" % (sym.rev_dep.name, sym.str_value)
    return dprint(sym.rev_dep)

def deprint(x):
    if type(x) == kconfiglib.Choice:
        return "%s:%s" % (x.name, x.str_value)
    s1 = x[1]
    if type(x[1]) == tuple:
        st1 = deprint(x[1])
    if type(x[1]) == kconfiglib.Symbol:
        s = x[1]
        if args.debug:
            print("depend on %s %s" % (s.name, s.str_value))
        if s.str_value == 'n':
            st1 = "%s:%s" % (s.name, s.str_value)
        st1 = "%s:%s" % (s.name, s.str_value)
        if s.str_value == s.name:
            st1 = "!%s" % s.name
        #print("ST1: %s" % st1)
    if len(x) == 2:
        if x[0] == NOT:
            print(x)
            return "%s!=%s" % (s.name, s.str_value)
        return st1
    s2 = x[2]
    if type(x[2]) == kconfiglib.Choice:
        st2 = "%s:%s" % (x[2].name, x[2].str_value)
    if type(x[2]) == kconfiglib.Symbol:
        s = x[2]
        if args.debug:
            print("2 depend on %s %s" % (s.name, s.str_value))
        if s.str_value == 'n':
            st2 = "%s:%s" % (s.name, s.str_value)
        st2 = "%s:%s" % (s.name, s.str_value)
        if s.str_value == s.name:
            st2 = "!%s" % s.name
    if type(x[2]) == tuple:
        st2 = deprint(x[2])
    if x[0] == AND:
        fs = st1 + " AND " + st2
        return fs
    elif x[0] == OR:
        fs = st1 + " OR " + st2
        return fs
    elif x[0] == EQUAL:
        if x[1].str_value != s2.str_value:
            return "%s = %s" % (s1.name, s2.name)
        return ""
    elif x[0] == UNEQUAL:
        if x[1].str_value == s2.str_value:
            return "%s = %s" % (s1.name, s2.name)
        return ""
    else:
        print("UNKNOWN %d" % x[0])
    return "ERROR"


def directdep(sym):
    if not sym.direct_dep:
        return ""
    if type(sym.direct_dep) == kconfiglib.Symbol:
        if sym.direct_dep.name == 'y':
            return ""
        return "DEPENDS on %s:%s" % (sym.direct_dep.name, sym.direct_dep.str_value)
    return "DEPENDS on %s" % deprint(sym.direct_dep)

def config_set(name, typ, defconfig, xset):
    if name not in configs["configs"]:
        configs["configs"][name] = {}
    if defconfig:
        if not defconfig in configs["configs"][name]:
            configs["configs"][name][defconfig] = {}
        configs["configs"][name][defconfig][typ] = xset
    else:
        configs["configs"][name][typ] = xset
    with open('%s/configs.yaml' % configdir, 'w') as rfile:
        yaml.dump(configs, rfile, default_flow_style=False)

def config_get(name, defconfig, typ):
    if name not in configs["configs"]:
        return False
    if defconfig and defconfig in configs["configs"][name]:
        if typ in configs["configs"][name][defconfig]:
            return configs["configs"][name][defconfig][typ]
    if typ in configs["configs"][name]:
        return configs["configs"][name][typ]
    return False

def configable(sym):
    if sym.user_value is None:
        if sym.assignable:
            return True
        if args.debug:
            print("========================")
            print("NOT %s:%s" % (sym.name, sym.str_value))
            print(sym.assignable)
            print(directdep(sym))
        #if sym.assignable or sym.type == 27:
        return False
    return True

def main(stdscr):
    cmd = 0
    curses.init_pair(L_RED, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(L_GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(L_BLUE, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(L_WHITE, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(L_CYAN, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(L_YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(L_TGT, curses.COLOR_GREEN, curses.COLOR_WHITE)
    curses.init_pair(L_INPUT, curses.COLOR_BLACK, curses.COLOR_WHITE)
    stdscr.timeout(50)
    needexit = False
    swin = None
    arch = None
    srcarch = None
    defconfig = None
    if args.arch:
        srcarch = args.arch
        if args.defconfig:
            defconfig = args.defconfig
    archlist = []
    p = 0
    offset = 0
    pad = None
    cur = ""
    search = ""
    insearch = 0
    search_firstfound = -1
    search_found = 0
    filters = []
    while not needexit:
        #now = time.time()
        rows, cols = stdscr.getmaxyx()
        if not swin:
            swin = curses.newwin(rows, cols, 0, 0)
        swin.erase()
        swin.addstr(0, 0, "Screen %dx%d ARCH: %s SRCARCH: %s Defconfig: %s Source: %s y%d of%d" % (cols, rows, arch, srcarch, defconfig, sourcedir, p, offset))
        if srcarch is None:
            if pad is None:
                os.chdir(sourcedir)
                dirs = os.listdir("arch")
                archlist = []
                for fdir in dirs:
                    if fdir in [ ".gitignore", "Kconfig" ]:
                        continue
                    archlist.append(fdir)
                pad = curses.newpad(100, 200)
            swin.addstr(2, 0, "Choose arch:")
            y = 0
            if p < 0:
                p = 0
            if p >= len(archlist) - 1:
                p = len(archlist) - 1
            for a in archlist:
                if p == y:
                    pad.addstr(y, 0, "x %s" % a)
                else:
                    pad.addstr(y, 0, "  %s" % a)
                y += 1
        if srcarch is not None and defconfig is None:
            if pad is None:
                defconfig_list = []
                os.chdir(sourcedir)
                dirs = os.listdir("arch/%s/configs/" % srcarch)
                for fdir in dirs:
                    if fdir in [ ".gitignore" ]:
                        continue
                    defconfig_list.append(fdir)
                pad = curses.newpad(len(defconfig_list), 200)
            swin.addstr(2, 0, "Choose defconfig: (%d)" % len(defconfig_list))
            y = 0
            if p < 0:
                p = 0
            if p >= len(defconfig_list) - 1:
                p = len(defconfig_list) - 1
            for a in defconfig_list:
                if p + offset == y:
                    pad.addstr(y, 0, "x %s" % a)
                else:
                    pad.addstr(y, 0, "  %s" % a)
                y += 1

        if defconfig != None:
            if pad is None:
                kconf = kconfiglib.Kconfig("Kconfig", suppress_traceback=True, warn_to_stderr=False)
                kconf.load_config("arch/%s/configs/%s" % (srcarch, defconfig))
                pad = curses.newpad(len(kconf.unique_defined_syms), 200)
                ipad = curses.newpad(200, 200)
            swin.addstr(2, 0, "Choose config: (%d) curr=%s" % (len(kconf.unique_defined_syms), cur))
            y = 0
            if p < 0:
                p = 0
            if p >= len(kconf.unique_defined_syms) - 1:
                p = len(kconf.unique_defined_syms) - 1
            for sym in kconf.unique_defined_syms:
                #if not sym.assignable and sym.type != STRING and sym.type != HEX:
                #    continue
                #if sym.str_value == "":
                if not configable(sym):
                    continue
                if "notno" in filters:
                    if sym.str_value == 'n':
                        continue
                x = 2
                buf = "  "
                if sym.user_value is None:
                    x = 4
                if p + offset == y:
                    buf = "x "
                    cur = sym.name
                    ipad.erase()
                    ipad.addstr(10, 0, str(sym))
                    #ipad.addstr(1, 0, prdep(sym))
                    #ipad.addstr(5, 0, directdep(sym))
                    st = expr_str(sym.rev_dep, sc_expr_str_fn=my_sc_expr_str)
                    if st != "n:n":
                        ipad.addstr(1, 0 , "SELECTED by %s" % st)
                    st = expr_str(sym.direct_dep, sc_expr_str_fn=my_sc_expr_str)
                    if st != "y:y":
                        ipad.addstr(5, 0 , "DEPEND ON %s" % st)
                color = L_WHITE
                if config_get(sym.name, defconfig, "debug"):
                    color = L_YELLOW
                if config_get(sym.name, defconfig, "harden"):
                    color = L_GREEN
                if config_get(sym.name, defconfig, "need"):
                    color = L_RED
                cole = 0
                if sym.str_value == 'y':
                    cole = curses.A_BOLD
                pad.addstr(y, 0, buf)
                pad.addstr(y, x, "%s %s  " % (sym.name, sym.str_value), curses.color_pair(color) + cole)
                y += 1
            wmax = y

        if insearch == 1:
            swin.addstr(1, 0, "SEARCH: %s  " % search)
        if insearch > 1:
            swin.addstr(1, 0, "SEARCH: %s searchn=%d search_found=%d search_firstfound=%d" % (search, searchn, search_found, search_firstfound))

        swin.noutrefresh()
        if pad:
            pad.noutrefresh(offset, 0, 4, 0, rows - 1, cols - 1)
        if ipad:
            ipad.noutrefresh(0, 0, 5, 50, rows - 1, cols - 1)
        curses.doupdate()

        c = stdscr.getch()
        if insearch == 1:
            if c == 8 or c == 127 or c == curses.KEY_BACKSPACE:
                if len(search) > 0:
                    search = search[:-1]
            if c == curses.KEY_ENTER or c == 10 or c == 13:
                searchn = 1
                insearch = 2
                if len(search) == 0:
                    insearch = 0
        if c == ord(","):
            if len(search) > 0:
                insearch = 2
                searchn += 1
        if insearch == 2:
            y = 0
            search_firstfound = -1
            search_found = 0
            for sym in kconf.unique_defined_syms:
                #if not sym.assignable and sym.type != STRING and sym.type != HEX:
                #    continue
                #if sym.str_value == "":
                if not configable(sym):
                    continue
                if "notno" in filters:
                    if sym.str_value == 'n':
                        continue
                if re.search(".*%s.*" % search, sym.name):
                    search_found += 1
                    if search_firstfound == -1:
                        search_firstfound = y
                    if search_found == searchn:
                        p = y;
                        offset = 0
                y += 1
            if search_firstfound >= 0 and search_found < searchn:
                p = search_firstfound
                searchn = 1
            insearch = 3
        if insearch == 1:
            if c > 0 and c < 256 and (chr(c).isalnum() or c == ord("_")):
                search += chr(c)
            c = -1
        if c == 27 or c == ord('q'):
            needexit = True
        if c == curses.KEY_UP:
            p -= 1
        if c == curses.KEY_DOWN:
            p += 1
        if c == curses.KEY_PPAGE:
            p -= 20
        if c == curses.KEY_NPAGE:
            p += 20
        if p < 0:
            if offset > 0:
                offset += p
            if offset < 0:
                offset = 0
            p = 0
        if p > rows - 5:
            offset += p - (rows - 5)
            p = rows - 5
        if c == curses.KEY_F5:
            p = 0
            offset = 0
            if "notno" in filters:
                filters.remove("notno")
                pad.erase()
            else:
                filters.append("notno")
                pad.erase()
        if c == curses.KEY_F1:
            srcarch = None
            defconfig = None
            defconfig_list = None
            pad = None
            swin.erase()
            p = 0 
            offset = 0
        if c == ord("o"):
            # save result
            with open('%s/arch/%s/configs/%s' % (sourcedir, srcarch, defconfig), 'w') as rfile:
                for sym in kconf.unique_defined_syms:
                    #if not sym.assignable and sym.type != STRING and sym.type != HEX:
                        #rfile.write('IGNORE %s %d\n' % (sym.name, sym.type))
                    #    continue
                    if sym.user_value is None:
                        continue
                    #if sym.str_value == "":
                    #    continue
                    if sym.str_value == 'n':
                        rfile.write("# CONFIG_%s is not set\n" % sym.name)
                    elif sym.type == 47:
                        rfile.write('CONFIG_%s="%s"\n' % (sym.name, sym.str_value))
                    else:
                        rfile.write("CONFIG_%s=%s\n" % (sym.name, sym.str_value))
        if c == ord("s") or c == ord("S"):
            # save result
            with open('%s/config.out' % configdir, 'w') as rfile:
                for sym in kconf.unique_defined_syms:
                    #if not sym.assignable and sym.type != STRING and sym.type != HEX:
                        #rfile.write('IGNORE %s %d\n' % (sym.name, sym.type))
                    #    continue
                    if sym.user_value is None and c == ord("s"):
                        continue
                    if sym.str_value == "":
                        continue
                    if sym.str_value == 'n':
                        rfile.write("# CONFIG_%s is not set\n" % sym.name)
                    elif sym.type == 47:
                        rfile.write('CONFIG_%s="%s"\n' % (sym.name, sym.str_value))
                    else:
                        rfile.write("CONFIG_%s=%s\n" % (sym.name, sym.str_value))
        if c == ord("/"):
            insearch = 1
        if c == ord("*"):
            config_set(cur, "harden", None, True)
        if c == ord("-"):
            config_set(cur, "debug", None, True)
        if c == ord("r"):
            for sym in kconf.unique_defined_syms:
                if sym.name == cur:
                    sym.unset_value()
                    pad.erase()
        if c == ord("n"):
            for sym in kconf.unique_defined_syms:
                if sym.name == cur:
                    sym.set_value(0)
                    pad.erase()
        if c == ord("y"):
            for sym in kconf.unique_defined_syms:
                if sym.name == cur:
                    sym.set_value(2)
                    pad.erase()
        if c == ord(" "):
            if defconfig:
                config_set(cur, "need", defconfig, True)
            if srcarch is not None and defconfig is None:
                defconfig = defconfig_list[p + offset]
                pad = None
            if srcarch is None:
                srcarch = archlist[p + offset]
                pad = None
                os.environ["ARCH"] = srcarch
                os.environ["SRCARCH"] = srcarch
if not args.debug:
    wrapper(main)
    sys.exit(0)

print("START in %s" % sourcedir)

kconf = kconfiglib.Kconfig("Kconfig", suppress_traceback=False)
kconf.load_config("arch/%s/configs/%s" % (args.arch, args.defconfig))
with open('%s/%s-%s.load2' % (configdir, args.arch, args.defconfig), 'w') as rfile:
    for sym in kconf.unique_defined_syms:
        if sym.user_value is None:
            if not sym.assignable:
                continue
            continue
        if sym.str_value == 'n':
            rfile.write("# CONFIG_%s is not set\n" % sym.name)
        elif sym.type == 47:
            rfile.write('CONFIG_%s="%s"\n' % (sym.name, sym.str_value))
        else:
            rfile.write("CONFIG_%s=%s\n" % (sym.name, sym.str_value))

print(len(kconf.unique_defined_syms))
for sym in kconf.unique_defined_syms:
    if sym.user_value is None:
        if sym.assignable or sym.type == 27:
            toto = 1
            print("  %s %s" % (sym.name, sym.str_value))
        continue
    print("%s %s" % (sym.name, sym.str_value))
    if sym.rev_dep:
        if type(sym.rev_dep) == kconfiglib.Symbol:
            if sym.rev_dep.name == "n":
                continue
            print(sym.rev_dep)
            print(" %s SELECTED by %s:%s" % (sym.name, sym.rev_dep.name, sym.str_value))
            continue
        print("%s %s" % (sym.name, sym.str_value))
        fs = dprint(sym.rev_dep)
        print("=================")
        print(fs)
        print("=================")
