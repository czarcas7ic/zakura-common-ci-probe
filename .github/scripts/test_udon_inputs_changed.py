#!/usr/bin/env python3
"""Tests for udon_inputs_changed.py."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

import udon_inputs_changed

ROOT_MANIFEST = """
[workspace]
members = ["crates/bento", "crates/bento-core", "crates/bento-macros", "crates/udon", "crates/other"]

[workspace.package]
version = "{release}"
edition = "{edition}"

[workspace.dependencies]
bento = {{ package = "zakura-bento", version = "0.1.0", path = "crates/bento" }}
bento-core = {{ package = "zakura-bento-core", version = "0.1.0", path = "crates/bento-core" }}
bento-macros = {{ package = "zakura-bento-macros", version = "0.1.0", path = "crates/bento-macros" }}
other = {{ package = "zakura-other", version = "{release}", path = "crates/other" }}
{profile}
"""

MEMBER_MANIFEST = """
[package]
name = "{name}"
version = "0.1.0"
edition.workspace = true

[dependencies]
{dependencies}
"""


def package(name, version, *, source=None, dependencies=(), replace=None):
    """Returns one `[[package]]` lockfile entry."""
    lines = ["[[package]]", f'name = "{name}"', f'version = "{version}"']
    if source:
        lines.append(f'source = "{source}"')
    if replace:
        lines.append(f'replace = "{replace}"')
    if dependencies:
        lines.append("dependencies = [")
        lines.extend(f'    "{dependency}",' for dependency in dependencies)
        lines.append("]")
    return "\n".join(lines)


REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


class UdonInputsChangedTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.previous_directory = os.getcwd()
        os.chdir(self.root)
        self.git("init", "-q")
        self.git("config", "user.email", "ci@example.com")
        self.git("config", "user.name", "CI")

    def tearDown(self):
        os.chdir(self.previous_directory)
        self.temporary_directory.cleanup()

    def git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

    def commit(
        self,
        *,
        release="1.0.0",
        edition="2024",
        profile="",
        udon_dependencies="bento.workspace = true\nrand = \"0.8\"",
        lock_packages=None,
        lockfile=True,
    ):
        """Commits a small workspace and returns the commit hash."""
        files = {
            "Cargo.toml": ROOT_MANIFEST.format(
                release=release, edition=edition, profile=profile
            ),
            "crates/udon/Cargo.toml": MEMBER_MANIFEST.format(
                name="zakura-udon", dependencies=udon_dependencies
            ),
            "crates/bento/Cargo.toml": MEMBER_MANIFEST.format(
                name="zakura-bento",
                dependencies="bento-core.workspace = true\nbento-macros.workspace = true",
            ),
            "crates/bento-core/Cargo.toml": MEMBER_MANIFEST.format(
                name="zakura-bento-core", dependencies=""
            ),
            "crates/bento-macros/Cargo.toml": MEMBER_MANIFEST.format(
                name="zakura-bento-macros", dependencies="bento-core.workspace = true"
            ),
            "crates/other/Cargo.toml": MEMBER_MANIFEST.format(
                name="zakura-other", dependencies="rand = \"0.9\""
            ),
        }
        if lock_packages is None:
            lock_packages = self.lock_packages()
        if lockfile:
            files["Cargo.lock"] = "version = 4\n\n" + "\n\n".join(lock_packages) + "\n"
        elif (self.root / "Cargo.lock").exists():
            (self.root / "Cargo.lock").unlink()
        for path, contents in files.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(contents))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "commit")
        return self.git("rev-parse", "HEAD")

    def lock_packages(
        self,
        *,
        udon_rand="rand 0.8.5",
        rand_08_dependencies=("rand_core",),
        rand_core="0.6.4",
        other_rand="rand 0.9.2",
        other_version="1.0.0",
        include_rand_09=True,
        udon_name="zakura-udon",
        udon_extra=(),
    ):
        """Returns lockfile entries for the small workspace."""
        packages = [
            package("zakura-bento", "0.1.0", dependencies=["zakura-bento-core", "zakura-bento-macros"]),
            package("zakura-bento-core", "0.1.0"),
            package("zakura-bento-macros", "0.1.0", dependencies=["zakura-bento-core"]),
            package(udon_name, "0.1.0", dependencies=[udon_rand, "zakura-bento", *udon_extra]),
            package("zakura-other", other_version, dependencies=[other_rand]),
            package("rand", "0.8.5", source=REGISTRY, dependencies=rand_08_dependencies),
            package("rand_core", rand_core, source=REGISTRY),
        ]
        if include_rand_09:
            packages.append(package("rand", "0.9.2", source=REGISTRY))
        return packages

    def changed(self, base, head):
        return udon_inputs_changed.udon_inputs_changed(base, head)

    def test_identical_inputs_are_unchanged(self):
        base = self.commit()
        head = self.commit()
        self.assertFalse(self.changed(base, head))

    def test_release_of_other_crates_is_unchanged(self):
        base = self.commit()
        head = self.commit(
            release="1.1.0", lock_packages=self.lock_packages(other_version="1.1.0")
        )
        self.assertFalse(self.changed(base, head))

    def test_inherited_package_key_is_changed(self):
        base = self.commit()
        head = self.commit(edition="2021")
        self.assertTrue(self.changed(base, head))

    def test_inherited_dependency_is_changed(self):
        base = self.commit()
        head = self.commit()
        manifest = (self.root / "Cargo.toml").read_text().replace(
            'path = "crates/bento" }', 'path = "crates/bento", features = ["std"] }'
        )
        (self.root / "Cargo.toml").write_text(manifest)
        self.git("commit", "-q", "-am", "bento features")
        self.assertTrue(self.changed(base, self.git("rev-parse", "HEAD")))
        self.assertFalse(self.changed(base, head))

    def test_profile_is_changed(self):
        base = self.commit()
        head = self.commit(profile="[profile.test.package.zakura-other]\nopt-level = 3")
        self.assertTrue(self.changed(base, head))

    def test_reachable_lockfile_entry_is_changed(self):
        base = self.commit()
        head = self.commit(lock_packages=self.lock_packages(rand_core="0.6.5"))
        self.assertTrue(self.changed(base, head))

    def test_unreachable_lockfile_entry_is_unchanged(self):
        base = self.commit()
        head = self.commit(lock_packages=self.lock_packages(other_rand="rand 0.8.5", include_rand_09=False))
        self.assertFalse(self.changed(base, head))

    def test_shortened_reference_to_same_package_is_unchanged(self):
        # Dropping the unrelated rand 0.9 lets Cargo spell rand 0.8 as "rand".
        base = self.commit()
        head = self.commit(
            lock_packages=self.lock_packages(
                udon_rand="rand", other_rand="rand", include_rand_09=False
            )
        )
        self.assertFalse(self.changed(base, head))

    def test_missing_lockfile_is_changed(self):
        base = self.commit(lockfile=False)
        head = self.commit()
        self.assertTrue(self.changed(base, head))

    def test_replacement_dependencies_are_compared(self):
        git_source = "git+https://example.com/rand#0123456789abcdef"

        def replaced(rand_core):
            registry_rand = f"rand 0.8.5 ({REGISTRY})"
            packages = self.lock_packages(
                udon_rand=registry_rand, other_rand=registry_rand, include_rand_09=False
            )
            packages[5] = package(
                "rand", "0.8.5", source=REGISTRY, replace=f"rand 0.8.5 ({git_source})"
            )
            packages.append(
                package("rand", "0.8.5", source=git_source, dependencies=[f"rand_core {rand_core}"])
            )
            packages.append(package("rand_core", "0.6.5", source=REGISTRY))
            return packages

        base = self.commit(lock_packages=replaced("0.6.4"))
        head = self.commit(lock_packages=replaced("0.6.5"))
        self.assertTrue(self.changed(base, head))

    def test_missing_member_manifest_fails(self):
        base = self.commit()
        self.git("rm", "-q", "crates/bento-core/Cargo.toml")
        self.git("commit", "-q", "-m", "drop manifest")
        with self.assertRaisesRegex(ValueError, "crates/bento-core/Cargo.toml"):
            self.changed(base, self.git("rev-parse", "HEAD"))

    def test_renamed_package_fails(self):
        base = self.commit()
        head = self.commit(lock_packages=self.lock_packages(udon_name="zakura-udon-renamed"))
        with self.assertRaisesRegex(ValueError, "zakura-udon"):
            self.changed(base, head)

    def test_dependency_on_another_member_fails(self):
        base = self.commit()
        head = self.commit(lock_packages=self.lock_packages(udon_extra=["zakura-other"]))
        with self.assertRaisesRegex(ValueError, "zakura-other"):
            self.changed(base, head)

    def test_unknown_revision_fails(self):
        head = self.commit()
        with self.assertRaises(subprocess.CalledProcessError):
            self.changed("0" * 40, head)


if __name__ == "__main__":
    unittest.main()
