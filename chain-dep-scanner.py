#!/usr/bin/python

import os
import os.path
from os.path import basename, dirname
import re

WORLD = "/var/lib/portage/world"
PKGDIR = "/var/db/pkg"

TARGET_REGEXP = r"^((?:ruby|python)_targets_|python_single_target_|abi_x86_)"


def world_pkgs():
    """Return the list of world packages
    """
    with open(WORLD) as f:
        return f.read().split()


def use_disabled(use):
    """Return if the USE flag is disabled form

    >>> use_disabled("foo")
    False
    >>> use_disabled("-foo")
    True
    """
    return use.startswith("-")


def use_canonical(use):
    """Return canonical form of USE flag

    >>> use_canonical("python_targets_python3_6(-)")
    'python_targets_python3_6'
    """
    if use.endswith("(-)"):
        return use[:-3]
    if use.endswith("(+)"):
        return use[:-3]
    return use


def pkg_canonical(pkg):
    """Returns canonical form of package name

    >>> pkg_canonical("dev-python/python-slip-0.6.5:0")
    'dev-python/python-slip:0'
    >>> pkg_canonical(">=dev-python/python-slip-0.2.7")
    'dev-python/python-slip:0'
    >>> pkg_canonical(">=dev-lang/python-exec-2:2/2=")
    'dev-lang/python-exec:2'
    >>> pkg_canonical("x11-libs/libSM")
    'x11-libs/libSM:0'
    """
    m = re.match(r"^(?:[<=>~]+)?([^/]+)/([^:]+)(?::([^/]*))?", pkg)
    cat = m.group(1)
    pnbase = m.group(2)
    slot = m.group(3)
    m = re.match("(.*)-(?:[0-9]+(\.[0-9]+)*)", pnbase)
    if m:
        pn = m.group(1)
    else:
        pn = pnbase
    if slot is None:
        slot = "0"
    return "%s/%s:%s" % (cat, pn, slot)


def build_rdepgraph():
    reg_target = re.compile(TARGET_REGEXP)
    reg_use = re.compile(r'^(.*)\[(.*)\]$')
    using_pkgs = {}
    use_deps = {}

    def add_rdep(use, deppkg, curpkg):
        if use not in use_deps:
            use_deps[use] = {}
        if deppkg not in use_deps[u]:
            use_deps[use][deppkg] = set()
        use_deps[use][deppkg].add(curpkg)

    for root, dirs, files in os.walk(PKGDIR):
        if "environment.bz2" not in files:
            continue

        with open(os.path.join(root, "SLOT")) as f:
            slot = f.read().strip().split("/")[0]
        cat = basename(dirname(root))
        pf = basename(root)
        curpkg = pkg_canonical("%s/%s:%s" % (cat, pf, slot))

        with open(os.path.join(root, "USE")) as f:
            iuse = f.read().split()

        with open(os.path.join(root, "USE")) as f:
            for u in f.read().split():
                if u not in iuse:
                    continue
                if not reg_target.match(u):
                    continue
                if u not in using_pkgs:
                    using_pkgs[u] = []
                using_pkgs[u].append(curpkg)

        for fn in files:
            if not fn.endswith("DEPEND"):
                continue
            with open(os.path.join(root, fn)) as f:
                for d in f.read().split():
                    m = reg_use.search(d)
                    if not m:
                        continue
                    deppkg = pkg_canonical(m.group(1))
                    if deppkg.startswith("!"):
                        continue
                    for u in m.group(2).split(","):
                        if use_disabled(u):
                            continue
                        u = use_canonical(u)
                        if not reg_target.match(u):
                            continue
                        add_rdep(u, deppkg, curpkg)

    return (use_deps, using_pkgs)


def inworld(pkg, world):
    pkg_without_slot = pkg.split(":")[0]
    return pkg in world or pkg_without_slot in world


def main():
    wpkgs = world_pkgs()
    wpkgs.extend(["dev-vcs/git"])
    use_rdeps, using_pkgs = build_rdepgraph()
    for u in using_pkgs:
        rdep = use_rdeps.get(u, {})
        pkgs = using_pkgs[u]
        world_deps = {}
        for p in pkgs:
            world_deps[p] = set()
            toscan = set([p])
            visit = set()
            while toscan:
                head = toscan.pop()
                if head in visit:
                    continue
                visit.add(head)
                if head in world_deps and head != p:
                    world_deps[p] |= world_deps[head]
                    continue
                if inworld(head, wpkgs):
                    world_deps[p].add(head)
                    continue
                toscan |= rdep.get(head, set())
            if not world_deps[p]:
                print("%s[%s] is not pulled by any world packages" % (p, u))


if __name__ == "__main__":
    main()
