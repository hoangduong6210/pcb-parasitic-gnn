#!/usr/bin/env python3
"""
T-REAL — anchor our 3-D inductance extraction to a REAL commercial core.

The PFC worked example (textbook ch.13.3) targets ~600 uH on an EER40 GP95 ferrite
(Suzhou Wanda) PFC boost choke. EER40 GP95 has a datasheet ungapped
A_L = 7481 nH/N^2 and catalog gaps. We run the engine's validated 3-D
magnetostatic FEM on that exact core (Ae from the round centre post, le, mu from
the datasheet A_L) across the catalog gaps and check that the FEM A_L reproduces
the datasheet / analytical reluctance A_L. This validates the extraction physics
against a real measured commercial part, independent of the (unstated) final turn
count. We then report the turns that realise the 600 uH target.

3-D FEM is heavy -> Runs on a compute cluster.
"""
import json, math, platform
from pathlib import Path
from types import SimpleNamespace

MU0 = 4 * math.pi * 1e-7
ROOT = Path(__file__).resolve().parents[1]

# --- EER40 GP95 datasheet-anchored parameters ---
POST_DIA_MM = 13.3                      # round centre-post diameter (engine DB)
AE_MM2 = math.pi * (POST_DIA_MM / 2) ** 2   # ~138.9 mm^2
LE_MM = 84.0                           # EER40/22/15 effective path length
AL_UNGAPPED_NH = 7481.0                # engine DB / GP95 datasheet
MU_I = AL_UNGAPPED_NH * 1e-9 * (LE_MM * 1e-3) / (MU0 * AE_MM2 * 1e-6)  # ~3600
GAPS_MM = [0.05, 0.1, 0.2, 0.5, 1.0]
AW_MM2 = 150.0
L_TARGET_UH = 600.0
I_PK_A = 9.0
BSAT_T = 0.50


def analytical_AL_nH(gap_mm):
    """Reluctance-addition gapped A_L (nH/N^2), ignoring fringing."""
    inv = 1.0 / (AL_UNGAPPED_NH * 1e-9) + (gap_mm * 1e-3) / (MU0 * AE_MM2 * 1e-6)
    return 1.0 / inv * 1e9


def fem_AL_nH(gap_mm, refine=0):
    from engine.sim.skfem_magnetostatic_3d import solve_magnetostatic_3d
    N = 10
    core = SimpleNamespace(ae_mm2=AE_MM2, aw_mm2=AW_MM2, le_mm=LE_MM, mu_i=MU_I)
    design = SimpleNamespace(core=core, n_pri=N, n_sec=0, i_pri_pk_a=I_PK_A,
                             air_gap_mm=gap_mm)
    r = solve_magnetostatic_3d(design, refine=refine)
    lm_uh = getattr(r, "lm_uh", None) or getattr(r, "lm_uH", None)
    if lm_uh is None and isinstance(r, dict):
        lm_uh = r.get("lm_uh")
    return (float(lm_uh) * 1e3 / (N * N)) if lm_uh else None   # nH/N^2


def main():
    print("[pfc] EER40 GP95: Ae=%.1f mm^2, le=%.0f mm, mu_i=%.0f, AL_ung=%.0f nH"
          % (AE_MM2, LE_MM, MU_I, AL_UNGAPPED_NH))
    rows = []
    for g in GAPS_MM:
        ana = analytical_AL_nH(g)
        try:
            fem = fem_AL_nH(g)
        except Exception as e:
            fem = None; print("  gap %.2f FEM error: %s" % (g, e))
        err = round(abs(fem - ana) / ana * 100, 2) if fem else None
        # turns + peak B to realise 600 uH at this gap
        N600 = math.sqrt(L_TARGET_UH * 1e3 / ana) if ana > 0 else 0
        Bpk = L_TARGET_UH * 1e-6 * I_PK_A / (max(N600, 1) * AE_MM2 * 1e-6)
        rows.append({"gap_mm": g, "AL_analytical_nH": round(ana, 1),
                     "AL_fem_nH": round(fem, 1) if fem else None,
                     "fem_vs_analytical_pct": err,
                     "turns_for_600uH": round(N600, 1), "Bpk_T": round(Bpk, 3)})
        print("  gap=%.2f mm: AL_ana=%.1f, AL_fem=%s nH (%s%%), N600=%.0f, Bpk=%.2fT"
              % (g, ana, round(fem, 1) if fem else "NA", err, N600, Bpk))
    valid = [r["fem_vs_analytical_pct"] for r in rows if r["fem_vs_analytical_pct"] is not None]
    out = {"note": "3-D FEM AL vs datasheet/analytical AL for a real EER40 GP95 core "
                   "(PFC 600uH worked example, textbook ch.13.3)",
           "core": "EER40 GP95 (Suzhou Wanda)", "AL_ungapped_datasheet_nH": AL_UNGAPPED_NH,
           "Ae_mm2": round(AE_MM2, 1), "le_mm": LE_MM, "mu_i": round(MU_I),
           "host": platform.node(),
           "fem_vs_analytical_median_pct": round(float(sorted(valid)[len(valid)//2]), 2) if valid else None,
           "rows": rows}
    od = ROOT / "05_experiments" / "run_pfc"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_pfc.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
