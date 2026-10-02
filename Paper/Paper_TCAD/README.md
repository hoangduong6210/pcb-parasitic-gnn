# TCAD working draft

This is the editable manuscript for the proposed TCAD submission. Version
`0.1.0-tcad-draft` starts from Journal Snapshot 1.1.1 and adds the author-reported
use of OpenAI Codex for manuscript outlining, wording and sentence formulation.
It does not add scientific results or claim submission readiness.

The released [journal snapshot](../Paper_Journal_Snapshot_1/) is unchanged.
`DRAFT_PROVENANCE.json` records the base tag, commit and source hashes. Figures,
figure data, bibliography and IEEEtran assets retain the base snapshot bytes.
The draft deliberately has no `SNAPSHOT_MANIFEST.json` or release tag: its
current tracked hashes belong to the repository-level manifest.

Build from the repository root:

```bash
bash Paper/Paper_TCAD/build.sh
```

The output is [PCB_Parasitic_GNN_TCAD_Draft.pdf](build/PCB_Parasitic_GNN_TCAD_Draft.pdf).
The existing figure generator remains available for reproducing inherited
figures; no figure or numerical result was regenerated for the disclosure edit.

The [AI disclosure record](../../wiki/manuscript/AI-Disclosure.md) owns the
author-reported wording. The [TCAD research plan](../../wiki/manuscript/TCAD-Research-Plan.md)
describes proposed studies. New results must pass the wiki claim-admission
process before being added here. The final disclosure must be checked against
the actual scope of assistance used throughout submission preparation.
