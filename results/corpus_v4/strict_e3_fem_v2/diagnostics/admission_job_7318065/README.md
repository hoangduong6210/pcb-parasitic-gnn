# Validation replay failure

Admission job `7318065` ran on `a0210` from 2026-09-15 05:39:51 to
05:40:18 EDT. Accounting reports `FAILED`, exit `1:0`, elapsed 27 s and zero
restarts. The execution source is `efeb123c9975ae481d10cd7c0af899406c46e787`.

The preserved stderr identifies a numeric mismatch while reconstructing
validation metrics from a saved checkpoint. The comparison uses relative
tolerance `1e-8` and absolute tolerance `1e-10`. The original exception does
not identify the metric or differing values. No accepted set was written.

All 25 training tasks in array `7318063` completed successfully and produced
75 checkpoint files. Their admission is still pending. A separate diagnostic
will compare validation replay using two and eight numerical threads, with
two fresh processes per setting on task zero and all three arms. It will
retain individual differences under the original comparison rule. This
diagnostic cannot admit checkpoints, change tolerance, or authorize test
inference. The frozen training artifacts remain the source of any recovery.
