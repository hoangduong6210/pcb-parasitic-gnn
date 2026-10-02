# Manuscript packages

All manuscript packages live under this directory. The [research wiki](../wiki/)
remains the canonical source for scientific claims and current project status.

| Package | Status | PDF |
|---|---|---|
| [Paper_Journal_Snapshot_1](Paper_Journal_Snapshot_1/) | Current journal snapshot, version 1.1.1 | [Journal PDF](Paper_Journal_Snapshot_1/build/PCB_Parasitic_GNN_Journal_Snapshot_1.pdf) |
| [Paper_Summary](Paper_Summary/) | Superseded conference archive | [Archived submission](Paper_Summary/Conference_Submission_ARCHIVE.pdf) |
| [Paper_Full](Paper_Full/) | Superseded extended manuscript | [Archived extended PDF](Paper_Full/build/Paper_Full.pdf) |

The journal package was relocated byte-for-byte, including its snapshot
manifest. Published release tags retain their original directory layout.
The historical manuscript sources, figures and PDFs are also unchanged;
archive build wrappers and documentation links account for the new location.

From the repository root, verify the existing journal package with:

```bash
python3 Paper/Paper_Journal_Snapshot_1/verify_snapshot.py
```

To build from its LaTeX source:

```bash
bash Paper/Paper_Journal_Snapshot_1/build.sh
```

Rebuilding with a different TeX toolchain can change PDF bytes. Preserve the
released manifest and use a separate working copy for manuscript revisions.
See the [paper export contract](../wiki/manuscript/Paper-Export-Contract.md)
and the [TCAD readiness review](../wiki/manuscript/TCAD-Readiness.md) before
preparing a new submission version.
