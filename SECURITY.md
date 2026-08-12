# Security policy

Please report a suspected vulnerability privately through GitHub's security
advisory interface for this repository. Do not open a public issue containing
credentials, private cluster paths, or exploit details.

Only load checkpoints distributed with a tagged release and verify their
SHA-256 entries in `MANIFEST.json`. The code uses PyTorch's restricted
`weights_only=True` loader; do not bypass that boundary for untrusted files.

External field-solver binaries are outside this repository's trust boundary.
Build them from their upstream source, record their hashes, and run heavy jobs
inside an isolated batch environment.
