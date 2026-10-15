#!/usr/bin/env python3

"""Report whether root manifest or lockfile changes reach Udon and Bento.

CI routes every change to the root `Cargo.toml` or `Cargo.lock` to every
suite. Udon and Bento read only a small part of either file, so a dependency
bump or release elsewhere in the workspace leaves their build unchanged. This
compares that part between two revisions and prints `true` when it differs:

- the root manifest, with `[workspace.package]` and `[workspace.dependencies]`
  narrowed to the keys the Udon and Bento manifests inherit, and
- every lockfile entry reachable from the Udon and Bento packages. Cargo
  records all of a package's dependencies here regardless of features or
  dependency kind, so this covers every build of these crates.

A missing root manifest or lockfile counts as changed. The script fails,
so CI runs the suite, when this scope no longer covers the crates: a member
manifest or package is missing, or they depend on another workspace member.
"""

import subprocess
import sys
import tomllib

PACKAGES = (
    "zakura-bento",
    "zakura-bento-core",
    "zakura-bento-macros",
    "zakura-udon",
)
MANIFESTS = (
    "crates/bento/Cargo.toml",
    "crates/bento-core/Cargo.toml",
    "crates/bento-macros/Cargo.toml",
    "crates/udon/Cargo.toml",
)
DEPENDENCY_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def read(revision, path):
    """Returns `path` at `revision`, or `None` when the path does not exist."""
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}:{path}"],
        stderr=subprocess.DEVNULL,
    )
    if exists.returncode != 0:
        # Distinguish a missing path from an unknown revision.
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{revision}^{{tree}}"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return None
    return subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout


def is_inherited(value):
    """Returns whether a manifest value is `{ workspace = true, ... }`."""
    return isinstance(value, dict) and value.get("workspace") is True


def inherited_keys(manifest_text):
    """Returns the package and dependency keys a member takes from the workspace."""
    manifest = tomllib.loads(manifest_text)
    package_keys = {
        key for key, value in manifest.get("package", {}).items() if is_inherited(value)
    }
    tables = [manifest, *manifest.get("target", {}).values()]
    dependency_keys = {
        key
        for table in tables
        for kind in DEPENDENCY_TABLES
        for key, value in table.get(kind, {}).items()
        if is_inherited(value)
    }
    return package_keys, dependency_keys


def manifest_view(manifest_text, package_keys, dependency_keys):
    """Returns the root manifest without workspace keys Udon and Bento ignore."""
    if manifest_text is None:
        return None
    manifest = tomllib.loads(manifest_text)
    workspace = manifest.get("workspace", {})
    for table, keys in (("package", package_keys), ("dependencies", dependency_keys)):
        if table in workspace:
            workspace[table] = {
                key: value for key, value in workspace[table].items() if key in keys
            }
    return manifest


def lockfile_view(lockfile_text):
    """Returns the lockfile entries reachable from the Udon and Bento packages."""
    if lockfile_text is None:
        return None
    lockfile = tomllib.loads(lockfile_text)
    packages = lockfile.get("package", [])

    def identity(package):
        return (package["name"], package["version"], package.get("source"))

    def resolve(reference):
        # Cargo writes "name", "name version", or "name version (source)",
        # adding only the parts needed to make the reference unambiguous.
        name, _, rest = reference.partition(" ")
        version, _, source = rest.partition(" ")
        matches = [
            package
            for package in packages
            if package["name"] == name
            and (not version or package["version"] == version)
            and (not source or f"({package.get('source')})" == source)
        ]
        if len(matches) != 1:
            raise ValueError(f"cannot resolve lockfile reference {reference!r}")
        return matches[0]

    pending = [
        package
        for package in packages
        if package["name"] in PACKAGES and "source" not in package
    ]
    missing = set(PACKAGES) - {package["name"] for package in pending}
    if missing:
        raise ValueError(f"lockfile has no workspace package {sorted(missing)}")
    reachable = {}
    while pending:
        package = pending.pop()
        if identity(package) in reachable:
            continue
        if "source" not in package and package["name"] not in PACKAGES:
            # Its manifest inherits workspace keys this scope does not read.
            raise ValueError(f"Udon and Bento depend on workspace package {package['name']}")
        references = package.get("dependencies", [])
        if "replace" in package:
            references = [*references, package["replace"]]
        dependencies = [resolve(reference) for reference in references]
        # Compare resolved identities rather than Cargo's reference spelling,
        # which shortens when an unrelated duplicate version leaves the graph.
        reachable[identity(package)] = {
            **package,
            "dependencies": sorted(identity(dependency) for dependency in dependencies),
        }
        pending.extend(dependencies)
    return {"version": lockfile.get("version"), "packages": reachable}


def udon_inputs_changed(base, head):
    """Returns whether Udon's view of the root manifest or lockfile changed."""
    package_keys, dependency_keys = set(), set()
    for revision in (base, head):
        for path in MANIFESTS:
            text = read(revision, path)
            if text is None:
                raise ValueError(f"{path} does not exist at {revision}")
            packages, dependencies = inherited_keys(text)
            package_keys |= packages
            dependency_keys |= dependencies

    views = {
        "Cargo.toml": lambda text: manifest_view(text, package_keys, dependency_keys),
        "Cargo.lock": lockfile_view,
    }
    for path, view in views.items():
        before = view(read(base, path))
        after = view(read(head, path))
        if before is None or after is None or before != after:
            return True
    return False


def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} BASE HEAD", file=sys.stderr)
        return 2
    print("true" if udon_inputs_changed(sys.argv[1], sys.argv[2]) else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
