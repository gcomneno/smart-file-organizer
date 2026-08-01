# Release procedure

GitHub Releases is the supported distribution channel.

Each release contains one pure-Python wheel, one source distribution, and a
`SHA256SUMS` file covering both artifacts. The release workflow runs only for a
tag named `v<package-version>`; the tag and `project.version` must match.

## Prepare and verify

Run formatting, lint, type checking, the complete test suite on Python 3.11 and
3.12, the reproducible build, and installed-wheel smoke tests before merging a
release preparation pull request.

The build script performs two independent builds using the commit timestamp as
`SOURCE_DATE_EPOCH`. Both wheel and source distribution must compare
byte-for-byte.

## Publish

After merging the reviewed release preparation into `main`, create and push an
annotated tag matching the package version. For version `0.4.0`, use `v0.4.0`.
The tag starts `.github/workflows/release.yml`, which rebuilds, verifies, smoke
tests, and attaches the artifacts to the GitHub Release.

## Verify downloaded artifacts

Download the wheel, source distribution, and `SHA256SUMS` into one empty
directory, then run:

~~~bash
sha256sum --check SHA256SUMS
~~~

A tag/version mismatch, non-reproducible build, checksum mismatch, failed smoke
test, or existing release with the same tag stops publication. Artifacts are
not silently replaced.
