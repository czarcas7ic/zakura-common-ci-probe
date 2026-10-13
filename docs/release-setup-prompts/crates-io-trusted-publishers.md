# Agent prompt: configure crates.io Trusted Publishers

Configure crates.io Trusted Publishing for every publishable workspace crate
in zakura-core/common.

Reference implementation:
https://github.com/zakura-core/common/pull/568

Use a clean, isolated checkout of current origin/main. Preserve existing local
edits and read the repository's instructions before acting.

Determine the selected crates from current Cargo metadata:

```sh
cargo metadata --locked --no-deps --format-version 1
```

Select only packages whose IDs are in workspace_members and whose publish
field is either null or an array containing "crates-io". Do not use a fixed
crate list. The previous inspection selected 24 of 28 members.

For every selected crate, ensure this exact GitHub Trusted Publisher exists:

```text
repository_owner: zakura-core
repository_name: common
workflow_filename: publish-crates.yml
environment: crates-io
```

Use Sean's existing authorized crates.io login or credential at runtime.
Never display credential values, put them in command arguments, or write
them into source or documentation. Do not create a new publishing token.

Inspect each crate's existing publishers first. Preserve all other
publishers and add the requested configuration only if it is absent.
zakura-reddsa-frost was already configured by the previous agent; read it
back and verify it rather than adding a duplicate.

Preferred UI:
crates.io → crate → Settings → Trusted Publishing

The crates.io API also supports:

```text
GET /api/v1/trusted_publishing/github_configs?crate=NAME&per_page=100
POST /api/v1/trusted_publishing/github_configs
```

POST body:

```json
{
  "github_config": {
    "crate": "NAME",
    "repository_owner": "zakura-core",
    "repository_name": "common",
    "workflow_filename": "publish-crates.yml",
    "environment": "crates-io"
  }
}
```

Follow pagination when present. Read back each configuration after adding
it, confirm the exact four publishing identity fields, and verify that
previous publishers remain present.

If the account does not own a crate, or a permission check denies access,
report the crate and blocker. Do not change ownership, delete publishers,
or retry using another identity.

Return a per-crate report: already correct, added and verified, or blocked.
Do not publish any crate, change versions, create tags, or merge a PR.
