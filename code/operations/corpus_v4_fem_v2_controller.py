#!/usr/bin/env python3
"""Login-safe SLURM controller and watcher for Corpus-v4 FEM-v2 production.

The controller never imports or invokes a field solver.  It submits only the
frozen source and finalizer batch wrappers, keeps the expanded submitted-job
count below a conservative ceiling, and records terminal ``sacct`` evidence.
Scientific admission remains a separate, explicit operator action.
"""
from __future__ import annotations

import argparse
import fcntl
import getpass
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


ROOT = Path(__file__).resolve().parents[2]
STATE_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-controller-state.v1"
CONTROLLER_BINDING_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-controller-binding.v1"
TERMINAL_ACCOUNTING_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-terminal-accounting.v1"
PROTOCOL_RELATIVE = "protocols/corpus_v4_fem_v2_production_v1.json"
PLAN_RELATIVE = "results/corpus_v4/cps_reference_v2/production/v1/plan/plan.json"
LOCK_RELATIVE = "protocols/corpus_v4_fem_v2_production_lock_v1.json"
STATE_RELATIVE = "results/corpus_v4/cps_reference_v2/production/v1/controller/status.json"
R3_WRAPPER_RELATIVE = "code/jobs/submit_corpus_v4_fem_v2_r3.sh"
R4_WRAPPER_RELATIVE = "code/jobs/submit_corpus_v4_fem_v2_r4.sh"
FINALIZER_WRAPPER_RELATIVE = "code/jobs/submit_finalize_corpus_v4_fem_v2_wave.sh"
CONTROLLER_SOURCE_RELATIVE = "code/operations/corpus_v4_fem_v2_controller.py"
SOFT_SUBMIT_CEILING = 950
HARD_SUBMIT_LIMIT = 1000
ACCOUNT = "pgs0407"
PARTITION = "nextgen"
SACCT_FIELDS = (
    "JobID",
    "JobIDRaw",
    "State",
    "ExitCode",
    "Account",
    "Partition",
    "Timelimit",
    "NodeList",
    "Restarts",
    "ElapsedRaw",
    "ReqTRES",
    "AllocTRES",
)
TERMINAL_STATES = frozenset(
    {
        "BOOT_FAIL",
        "CANCELLED",
        "COMPLETED",
        "DEADLINE",
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "PREEMPTED",
        "REVOKED",
        "SPECIAL_EXIT",
        "TIMEOUT",
    }
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
JOB_ID_RE = re.compile(r"[0-9]+")
DENIED_EXPORT_NAMES = frozenset(
    {
        "BASH_ENV",
        "ENV",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "SHELLOPTS",
    }
)


class ControllerError(RuntimeError):
    """Raised when the operational state cannot advance safely."""


@dataclass(frozen=True)
class CommandResult:
    """Small subprocess result type used by real and injected runners."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Injectable command boundary; unit tests never use the real runner."""

    def run(self, command: Sequence[str]) -> CommandResult:
        """Execute one scheduler command without a shell."""


class SubprocessRunner:
    """Production command boundary for the four allowed SLURM clients."""

    _ALLOWED = frozenset({"sacct", "sbatch", "squeue"})

    def run(self, command: Sequence[str]) -> CommandResult:
        if not command or command[0] not in self._ALLOWED:
            raise ControllerError("controller attempted a non-scheduler command")
        completed = subprocess.run(
            list(command), capture_output=True, check=False, text=True
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class ControllerConfig:
    """Immutable controller inputs and capacity policy."""

    execution_root: Path
    state_path: Path
    source_commit: str
    protocol_sha256: str
    plan_sha256: str
    lock_sha256: str
    username: str
    soft_ceiling: int = SOFT_SUBMIT_CEILING
    hard_limit: int = HARD_SUBMIT_LIMIT
    account: str = ACCOUNT
    partition: str = PARTITION
    finalizer_script: Path | None = None
    extra_exports: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WaveSpec:
    """One exact, hash-pinned source array and its operational finalizer."""

    wave_id: str
    package_wave_id: int
    fidelity_id: str
    slug: str
    r3_index: int | None
    dispatch_path: Path
    dispatch_sha256: str
    expected_tasks: int
    canonical_task_indices: tuple[int, ...]
    throttle: int
    source_wrapper: Path
    requested_cpus: int
    requested_memory: str
    time_limit: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Replace one status file atomically and fsync both file and directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ControllerError(f"{label} is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ControllerError(f"cannot load {label}: {path}") from error
    if not isinstance(value, dict):
        raise ControllerError(f"{label} is not a JSON object")
    return value


def _within_root(root: Path, path: Path, label: str) -> Path:
    resolved_root = root.resolve()
    supplied = path.resolve() if path.is_absolute() else (resolved_root / path).resolve()
    if supplied != resolved_root and resolved_root not in supplied.parents:
        raise ControllerError(f"{label} escapes the execution root")
    return supplied


def _regular_path(root: Path, relative_or_absolute: Path, label: str) -> Path:
    path = _within_root(root, relative_or_absolute, label)
    if path.is_symlink() or not path.is_file():
        raise ControllerError(f"{label} is absent or not a regular file: {path}")
    return path


def _validate_pin(value: str, pattern: re.Pattern[str], label: str) -> None:
    if pattern.fullmatch(value) is None:
        raise ControllerError(f"{label} is malformed")


def _parse_tres(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in value.split(","):
        if "=" in item:
            name, raw = item.split("=", 1)
            parsed[name] = raw
    return parsed


def _normalized_state(value: str) -> str:
    return value.split(maxsplit=1)[0].rstrip("+") if value else ""


def _parse_sacct(raw: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        values = line.split("|")
        if values and values[-1] == "":
            values.pop()
        if tuple(values) == SACCT_FIELDS:
            continue
        if len(values) != len(SACCT_FIELDS):
            raise ControllerError("sacct row field count differs")
        rows.append(dict(zip(SACCT_FIELDS, values)))
    return rows


def _validate_export_map(exports: Mapping[str, str]) -> None:
    for name, value in exports.items():
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is None:
            raise ControllerError(f"invalid exported variable name: {name}")
        if name in DENIED_EXPORT_NAMES or name.startswith("LD_"):
            raise ControllerError(f"runtime-control export is forbidden: {name}")
        if any(character in str(value) for character in (",", "\n", "\r")):
            raise ControllerError(f"exported value is unsafe for sbatch --export: {name}")


def _export_argument(exports: Mapping[str, str]) -> str:
    _validate_export_map(exports)
    # An explicit list avoids inheriting login-shell controls such as BASH_ENV,
    # PYTHONPATH, or LD_PRELOAD into the scientific batch job.
    return ",".join(f"{name}={exports[name]}" for name in sorted(exports))


def _expected_wave_layout() -> tuple[dict[str, Any], ...]:
    return (
        {
            "wave_id": "r4_000",
            "package_wave_id": 0,
            "fidelity_id": "cps_fem_r4_p16_t1_v2",
            "slug": "r4",
            "r3_index": None,
            "dispatch": "r4_dispatch_000.json",
            "tasks": 198,
            "indices": tuple(range(198)),
            "throttle": 2,
            "wrapper": R4_WRAPPER_RELATIVE,
            "cpus": 1,
            "memory": "160G",
            "time_limit": "03:00:00",
        },
        *tuple(
            {
                "wave_id": f"r3_{index:03d}",
                "package_wave_id": index,
                "fidelity_id": "cps_fem_r3_p16_t1_v2",
                "slug": "r3",
                "r3_index": index,
                "dispatch": f"r3_dispatch_{index:03d}.json",
                "tasks": size,
                "indices": tuple(range(start, start + size)),
                "throttle": 8,
                "wrapper": R3_WRAPPER_RELATIVE,
                "cpus": 1,
                "memory": "48G",
                "time_limit": "02:00:00",
            }
            for index, (start, size) in enumerate(
                ((0, 400), (400, 400), (800, 400), (1200, 300))
            )
        ),
    )


def build_wave_specs(config: ControllerConfig) -> tuple[WaveSpec, ...]:
    """Authenticate the five frozen dispatches without executing a solver."""

    root = config.execution_root.resolve()
    if not root.is_dir():
        raise ControllerError("execution root is not a directory")
    _validate_pin(config.source_commit, GIT_COMMIT_RE, "source commit")
    for label, value in (
        ("protocol SHA-256", config.protocol_sha256),
        ("plan SHA-256", config.plan_sha256),
        ("execution-lock SHA-256", config.lock_sha256),
    ):
        _validate_pin(value, SHA256_RE, label)
    if not 0 < config.soft_ceiling <= config.hard_limit <= HARD_SUBMIT_LIMIT:
        raise ControllerError("capacity ceilings are inconsistent or exceed hard QOS")
    if config.account != ACCOUNT or config.partition != PARTITION:
        raise ControllerError("account or partition differs from the frozen controller")
    if not config.username or any(character.isspace() for character in config.username):
        raise ControllerError("scheduler username is malformed")

    protocol = _regular_path(root, Path(PROTOCOL_RELATIVE), "protocol")
    plan_path = _regular_path(root, Path(PLAN_RELATIVE), "plan")
    lock = _regular_path(root, Path(LOCK_RELATIVE), "execution lock")
    if sha256_file(protocol) != config.protocol_sha256:
        raise ControllerError("protocol SHA-256 differs from the explicit pin")
    if sha256_file(plan_path) != config.plan_sha256:
        raise ControllerError("plan SHA-256 differs from the explicit pin")
    if sha256_file(lock) != config.lock_sha256:
        raise ControllerError("execution-lock SHA-256 differs from the explicit pin")

    finalizer = config.finalizer_script or Path(FINALIZER_WRAPPER_RELATIVE)
    finalizer_path = _regular_path(root, finalizer, "wave finalizer wrapper")
    canonical_finalizer = _regular_path(
        root, Path(FINALIZER_WRAPPER_RELATIVE), "canonical wave finalizer wrapper"
    )
    if finalizer_path != canonical_finalizer:
        raise ControllerError("only the canonical frozen finalizer wrapper is allowed")
    plan = _load_json_object(plan_path, "production plan")
    protocol_payload = _load_json_object(protocol, "production protocol")
    source_hashes = protocol_payload.get("computational_sources", {})
    required_controller_sources = {
        CONTROLLER_SOURCE_RELATIVE,
        R3_WRAPPER_RELATIVE,
        R4_WRAPPER_RELATIVE,
        FINALIZER_WRAPPER_RELATIVE,
    }
    if not required_controller_sources <= set(source_hashes):
        raise ControllerError("protocol omits the controller source closure")
    for relative in required_controller_sources:
        source = _regular_path(root, Path(relative), "controller computational source")
        if sha256_file(source) != source_hashes[relative]:
            raise ControllerError(f"controller computational source differs: {relative}")
    if (
        plan.get("schema") != "pcb-gnn.corpus-v4-fem-v2-production-plan.v1"
        or plan.get("counts")
        != {"geometries": 1500, "r3_tasks": 1500, "r4_tasks": 198}
        or not isinstance(plan.get("artifact_sha256"), dict)
    ):
        raise ControllerError("production plan identity or counts differ")

    specs: list[WaveSpec] = []
    for expected in _expected_wave_layout():
        dispatch_path = _regular_path(
            root, Path(PLAN_RELATIVE).parent / expected["dispatch"], "dispatch"
        )
        digest = plan["artifact_sha256"].get(expected["dispatch"])
        if not isinstance(digest, str) or sha256_file(dispatch_path) != digest:
            raise ControllerError(f"dispatch SHA-256 differs: {expected['dispatch']}")
        dispatch = _load_json_object(dispatch_path, "dispatch")
        entries = dispatch.get("entries")
        if (
            dispatch.get("schema")
            != "pcb-gnn.corpus-v4-fem-v2-production-dispatch.v1"
            or dispatch.get("fidelity_id") != expected["fidelity_id"]
            or not isinstance(entries, list)
            or len(entries) != expected["tasks"]
            or tuple(entry.get("task_index") for entry in entries)
            != expected["indices"]
            or any(not isinstance(entry.get("geometry_sha256"), str) for entry in entries)
        ):
            raise ControllerError(f"dispatch coverage differs: {expected['dispatch']}")
        wrapper = _regular_path(root, Path(expected["wrapper"]), "source wrapper")
        specs.append(
            WaveSpec(
                wave_id=expected["wave_id"],
                package_wave_id=expected["package_wave_id"],
                fidelity_id=expected["fidelity_id"],
                slug=expected["slug"],
                r3_index=expected["r3_index"],
                dispatch_path=dispatch_path,
                dispatch_sha256=digest,
                expected_tasks=expected["tasks"],
                canonical_task_indices=expected["indices"],
                throttle=expected["throttle"],
                source_wrapper=wrapper,
                requested_cpus=expected["cpus"],
                requested_memory=expected["memory"],
                time_limit=expected["time_limit"],
            )
        )
    return tuple(specs)


class FemV2Controller:
    """Fail-closed submission state machine with an embedded terminal watcher."""

    def __init__(
        self,
        config: ControllerConfig,
        runner: CommandRunner,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config
        self.root = config.execution_root.resolve()
        self.state_path = _within_root(self.root, config.state_path, "controller state")
        expected_state = (self.root / STATE_RELATIVE).resolve()
        if self.state_path != expected_state:
            raise ControllerError("controller state must use the canonical status path")
        current = self.state_path.parent
        while current != self.root:
            if current.exists() and current.is_symlink():
                raise ControllerError("controller state parent must not be a symlink")
            current = current.parent
        self.finalizer_script = _regular_path(
            self.root,
            config.finalizer_script or Path(FINALIZER_WRAPPER_RELATIVE),
            "wave finalizer wrapper",
        )
        self.specs = build_wave_specs(config)
        self.by_id = {spec.wave_id: spec for spec in self.specs}
        self.runner = runner
        self.now = now
        _validate_export_map(config.extra_exports)
        reserved = set(self._core_exports(self.specs[0])) | {
            "PCB_GNN_V4_FEM_V2_FIDELITY_ID",
            "PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION",
            "PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256",
            "PCB_GNN_V4_FEM_V2_SOURCE_BINDINGS",
            "PCB_GNN_V4_FEM_V2_WAVE_ID",
        }
        overlap = reserved.intersection(config.extra_exports)
        if overlap:
            raise ControllerError(f"extra exports override frozen values: {sorted(overlap)}")
        self.binding = self._build_binding()

    def _timestamp(self) -> str:
        return _iso_utc(self.now())

    def _build_binding(self) -> dict[str, Any]:
        return {
            "account": self.config.account,
            "execution_root": str(self.root),
            "finalizer_wrapper": str(self.finalizer_script),
            "hard_submit_limit": self.config.hard_limit,
            "lock_sha256": self.config.lock_sha256,
            "partition": self.config.partition,
            "plan_sha256": self.config.plan_sha256,
            "protocol_sha256": self.config.protocol_sha256,
            "schema": CONTROLLER_BINDING_SCHEMA,
            "soft_submit_ceiling": self.config.soft_ceiling,
            "source_commit": self.config.source_commit,
            "username": self.config.username,
            "waves": [
                {
                    "canonical_task_indices": list(spec.canonical_task_indices),
                    "dispatch": str(spec.dispatch_path),
                    "dispatch_sha256": spec.dispatch_sha256,
                    "expected_tasks": spec.expected_tasks,
                    "fidelity_id": spec.fidelity_id,
                    "source_wrapper": str(spec.source_wrapper),
                    "throttle": spec.throttle,
                    "wave_id": spec.wave_id,
                    "package_wave_id": spec.package_wave_id,
                }
                for spec in self.specs
            ],
        }

    def _new_state(self) -> dict[str, Any]:
        created = self._timestamp()
        return {
            "binding": self.binding,
            "capacity": {
                "hard_limit": self.config.hard_limit,
                "soft_ceiling": self.config.soft_ceiling,
            },
            "created_utc": created,
            "last_tick_utc": None,
            "operator_admission_required": True,
            "releases": {
                "events": [
                    {
                        "reason": "Gate-B authority frozen by the production protocol",
                        "released_r3_through": 0,
                        "type": "initial_protocol_authorization",
                        "utc": created,
                    }
                ],
                "r3_through": 0,
                "prior_admissions": {},
            },
            "schema": STATE_SCHEMA,
            "waves": {
                spec.wave_id: {
                    "dispatch_sha256": spec.dispatch_sha256,
                    "expected_tasks": spec.expected_tasks,
                    "fidelity_id": spec.fidelity_id,
                    "finalizer": {"status": "NOT_SUBMITTED"},
                    "source": {"status": "NOT_SUBMITTED"},
                }
                for spec in self.specs
            },
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._new_state()
        state = _load_json_object(self.state_path, "controller state")
        if state.get("schema") != STATE_SCHEMA or state.get("binding") != self.binding:
            raise ControllerError("controller state binding differs from current inputs")
        if set(state.get("waves", {})) != set(self.by_id):
            raise ControllerError("controller state wave inventory differs")
        releases = state.get("releases", {})
        if (
            type(releases.get("r3_through")) is not int
            or releases["r3_through"] not in range(4)
            or not isinstance(releases.get("events"), list)
            or not isinstance(releases.get("prior_admissions"), dict)
        ):
            raise ControllerError("controller release state is malformed")
        for wave_id, wave in state["waves"].items():
            if not isinstance(wave, dict):
                raise ControllerError("controller wave state is malformed")
            for kind in ("source", "finalizer"):
                job = wave.get(kind)
                if not isinstance(job, dict) or not isinstance(job.get("status"), str):
                    raise ControllerError("controller job state is malformed")
                job_id = job.get("job_id")
                if job_id is not None and (
                    not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None
                ):
                    raise ControllerError(f"controller {wave_id} {kind} JobID is malformed")
        return state

    def _save_state(self, state: Mapping[str, Any]) -> None:
        atomic_write_json(self.state_path, state)

    @contextmanager
    def _state_lock(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_path.with_suffix(self.state_path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _core_exports(self, spec: WaveSpec) -> dict[str, str]:
        return {
            "PCB_GNN_V4_EXECUTION_ROOT": str(self.root),
            "PCB_GNN_V4_FEM_V2_DISPATCH": str(spec.dispatch_path),
            "PCB_GNN_V4_FEM_V2_DISPATCH_SHA256": spec.dispatch_sha256,
            "PCB_GNN_V4_FEM_V2_PRODUCTION_LOCK_SHA256": self.config.lock_sha256,
            "PCB_GNN_V4_FEM_V2_PRODUCTION_PLAN_SHA256": self.config.plan_sha256,
            "PCB_GNN_V4_FEM_V2_PRODUCTION_PROTOCOL_SHA256": self.config.protocol_sha256,
            "PCB_GNN_V4_SOURCE_COMMIT": self.config.source_commit,
        }

    def _source_command(self, spec: WaveSpec) -> list[str]:
        exports = {**self.config.extra_exports, **self._core_exports(spec)}
        return [
            "sbatch",
            "--parsable",
            "-A",
            self.config.account,
            f"--chdir={self.root}",
            f"--array=0-{spec.expected_tasks - 1}%{spec.throttle}",
            f"--export={_export_argument(exports)}",
            str(spec.source_wrapper),
        ]

    def _prior_admission_for(
        self, state: Mapping[str, Any], spec: WaveSpec
    ) -> Mapping[str, str] | None:
        if spec.r3_index is None or spec.r3_index == 0:
            return None
        value = state["releases"]["prior_admissions"].get(str(spec.r3_index))
        if not isinstance(value, dict):
            raise ControllerError("released R3 wave lacks its prior admission binding")
        return value

    def _finalizer_command(
        self,
        state: Mapping[str, Any],
        spec: WaveSpec,
        source_job_id: str,
    ) -> list[str]:
        dispatch_relative = spec.dispatch_path.relative_to(self.root).as_posix()
        exports = {
            **self.config.extra_exports,
            **self._core_exports(spec),
            "PCB_GNN_V4_FEM_V2_FIDELITY_ID": spec.fidelity_id,
            "PCB_GNN_V4_FEM_V2_SOURCE_BINDINGS": (
                f"{source_job_id}|{dispatch_relative}|{spec.dispatch_sha256}"
            ),
            "PCB_GNN_V4_FEM_V2_WAVE_ID": str(spec.package_wave_id),
        }
        prior = self._prior_admission_for(state, spec)
        if prior is not None:
            exports["PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION"] = prior["path"]
            exports["PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256"] = prior["sha256"]
        return [
            "sbatch",
            "--parsable",
            "-A",
            self.config.account,
            f"--chdir={self.root}",
            f"--dependency=afterany:{source_job_id}",
            f"--export={_export_argument(exports)}",
            str(self.finalizer_script),
        ]

    def _squeue_snapshot(self) -> tuple[list[str], dict[str, Any]]:
        command = [
            "squeue",
            "-r",
            "-h",
            "-u",
            self.config.username,
            "-o",
            "%i",
        ]
        result = self.runner.run(command)
        if result.returncode != 0:
            raise ControllerError("expanded squeue query failed")
        identifiers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return identifiers, {
            "command": command,
            "expanded_live_count": len(identifiers),
            "queried_utc": self._timestamp(),
            "raw_stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
        }

    @staticmethod
    def _job_is_live(job_id: str, live_identifiers: Sequence[str]) -> bool:
        return any(value == job_id or value.startswith(job_id + "_") for value in live_identifiers)

    def _sacct_command(self, job_id: str) -> list[str]:
        return [
            "sacct",
            "-X",
            "-n",
            "-P",
            "-j",
            job_id,
            "--format=" + ",".join(SACCT_FIELDS),
        ]

    def _accounting_contract_errors(
        self,
        rows: Sequence[Mapping[str, str]],
        *,
        job_id: str,
        spec: WaveSpec,
        kind: str,
    ) -> list[str]:
        errors: list[str] = []
        if kind == "source":
            expected_ids = {f"{job_id}_{index}" for index in range(spec.expected_tasks)}
            observed_ids = [row["JobID"] for row in rows]
            if set(observed_ids) != expected_ids or len(observed_ids) != len(set(observed_ids)):
                errors.append("source JobID coverage differs")
            requested_cpus = spec.requested_cpus
            requested_memory = spec.requested_memory
            time_limit = spec.time_limit
        else:
            if len(rows) != 1 or rows[0]["JobID"] != job_id:
                errors.append("finalizer JobID differs")
            requested_cpus = 2
            requested_memory = "16G"
            time_limit = "00:30:00"
        raw_ids = [row["JobIDRaw"] for row in rows]
        if not all(raw_ids) or len(raw_ids) != len(set(raw_ids)):
            errors.append("JobIDRaw values are absent or duplicate")
        for row in rows:
            req = _parse_tres(row["ReqTRES"])
            alloc = _parse_tres(row["AllocTRES"])
            if row["Account"] != self.config.account:
                errors.append(f"{row['JobID']}: account differs")
            if row["Partition"] != self.config.partition:
                errors.append(f"{row['JobID']}: partition differs")
            if row["Timelimit"] != time_limit:
                errors.append(f"{row['JobID']}: time limit differs")
            if row["Restarts"] != "0":
                errors.append(f"{row['JobID']}: restart count differs")
            if not row["ElapsedRaw"].isdigit():
                errors.append(f"{row['JobID']}: elapsed time is malformed")
            if req.get("cpu") != str(requested_cpus) or req.get("mem") != requested_memory:
                errors.append(f"{row['JobID']}: requested TRES differs")
            if alloc.get("mem") != requested_memory:
                errors.append(f"{row['JobID']}: allocated memory differs")
            if not str(alloc.get("cpu", "")).isdigit() or int(alloc["cpu"]) < requested_cpus:
                errors.append(f"{row['JobID']}: allocated CPU count is invalid")
        return errors

    def _terminal_accounting(
        self, *, job_id: str, spec: WaveSpec, kind: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        command = self._sacct_command(job_id)
        result = self.runner.run(command)
        if result.returncode != 0:
            raise ControllerError(f"sacct query failed for {job_id}")
        rows = _parse_sacct(result.stdout)
        expected_rows = spec.expected_tasks if kind == "source" else 1
        probe = {
            "command": command,
            "expected_rows": expected_rows,
            "observed_rows": len(rows),
            "queried_utc": self._timestamp(),
            "raw_stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
        }
        if len(rows) != expected_rows or any(
            _normalized_state(row["State"]) not in TERMINAL_STATES for row in rows
        ):
            return None, probe
        canonical_rows = sorted(rows, key=lambda row: row["JobID"])
        errors = self._accounting_contract_errors(
            canonical_rows, job_id=job_id, spec=spec, kind=kind
        )
        terminal_success = all(
            _normalized_state(row["State"]) == "COMPLETED" and row["ExitCode"] == "0:0"
            for row in canonical_rows
        )
        evidence = {
            "canonical_rows": canonical_rows,
            "canonical_rows_sha256": sha256_bytes(canonical_json_bytes(canonical_rows)),
            "captured_utc": self._timestamp(),
            "command": command,
            "contract_errors": errors,
            "contract_pass": not errors,
            "expected_rows": expected_rows,
            "job_id": job_id,
            "kind": kind,
            "raw_stdout": result.stdout,
            "raw_stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
            "row_count": len(canonical_rows),
            "schema": TERMINAL_ACCOUNTING_SCHEMA,
            "terminal_success": terminal_success,
        }
        return evidence, probe

    def _refresh_accounting(
        self, state: dict[str, Any], live_identifiers: Sequence[str]
    ) -> None:
        for spec in self.specs:
            wave = state["waves"][spec.wave_id]
            for kind in ("source", "finalizer"):
                job = wave[kind]
                job_id = job.get("job_id")
                if not isinstance(job_id, str) or job.get("accounting") is not None:
                    continue
                if self._job_is_live(job_id, live_identifiers):
                    job["status"] = "LIVE"
                    continue
                evidence, probe = self._terminal_accounting(
                    job_id=job_id, spec=spec, kind=kind
                )
                job["last_accounting_probe"] = probe
                if evidence is None:
                    job["status"] = "ACCOUNTING_PENDING"
                else:
                    job["accounting"] = evidence
                    job["status"] = (
                        "TERMINAL"
                        if evidence["contract_pass"]
                        else "TERMINAL_CONTRACT_REJECTED"
                    )
                self._save_state(state)

    def _capacity_decision(self, live_count: int, new_elements: int) -> dict[str, Any]:
        projected = live_count + new_elements
        return {
            "allowed": projected <= self.config.soft_ceiling
            and projected <= self.config.hard_limit,
            "hard_limit": self.config.hard_limit,
            "live_expanded_elements": live_count,
            "new_elements": new_elements,
            "projected_expanded_elements": projected,
            "soft_ceiling": self.config.soft_ceiling,
        }

    @staticmethod
    def _parse_job_id(stdout: str) -> str:
        token = stdout.strip().split(";", 1)[0]
        if JOB_ID_RE.fullmatch(token) is None:
            raise ControllerError("sbatch --parsable returned an ambiguous job ID")
        return token

    def _submit_job(
        self,
        *,
        state: dict[str, Any],
        target: dict[str, Any],
        command: list[str],
        kind: str,
    ) -> str:
        target.update(
            {
                "command": command,
                "status": "SUBMITTING",
                "submission_intent_utc": self._timestamp(),
            }
        )
        self._save_state(state)
        result = self.runner.run(command)
        target["sbatch_stderr_sha256"] = sha256_bytes(result.stderr.encode("utf-8"))
        target["sbatch_stdout_sha256"] = sha256_bytes(result.stdout.encode("utf-8"))
        if result.returncode != 0:
            target["status"] = "SUBMISSION_FAILED"
            target["submission_returncode"] = result.returncode
            self._save_state(state)
            raise ControllerError(f"{kind} sbatch submission failed")
        try:
            job_id = self._parse_job_id(result.stdout)
        except ControllerError:
            target["status"] = "SUBMISSION_AMBIGUOUS"
            self._save_state(state)
            raise
        target.update(
            {
                "job_id": job_id,
                "status": "SUBMITTED",
                "submitted_utc": self._timestamp(),
                "submission_returncode": 0,
            }
        )
        self._save_state(state)
        return job_id

    def _submit_finalizer(
        self, state: dict[str, Any], spec: WaveSpec, live_count: int
    ) -> int:
        wave = state["waves"][spec.wave_id]
        source_job_id = wave["source"].get("job_id")
        if not isinstance(source_job_id, str):
            raise ControllerError("cannot submit a finalizer without a source job ID")
        decision = self._capacity_decision(live_count, 1)
        state["capacity"]["last_finalizer_decision"] = {
            **decision,
            "utc": self._timestamp(),
            "wave_id": spec.wave_id,
        }
        if not decision["allowed"]:
            wave["finalizer"]["status"] = "CAPACITY_BLOCKED"
            self._save_state(state)
            return live_count
        command = self._finalizer_command(state, spec, source_job_id)
        self._submit_job(
            state=state,
            target=wave["finalizer"],
            command=command,
            kind=f"{spec.wave_id} finalizer",
        )
        return live_count + 1

    def _submit_wave_pair(
        self, state: dict[str, Any], spec: WaveSpec, live_count: int
    ) -> int:
        decision = self._capacity_decision(live_count, spec.expected_tasks + 1)
        state["capacity"]["last_source_decision"] = {
            **decision,
            "utc": self._timestamp(),
            "wave_id": spec.wave_id,
        }
        if not decision["allowed"]:
            state["waves"][spec.wave_id]["source"]["status"] = "CAPACITY_BLOCKED"
            self._save_state(state)
            return live_count
        wave = state["waves"][spec.wave_id]
        source_job_id = self._submit_job(
            state=state,
            target=wave["source"],
            command=self._source_command(spec),
            kind=f"{spec.wave_id} source",
        )
        live_count += spec.expected_tasks
        if not source_job_id:  # pragma: no cover - guarded by parser
            raise AssertionError("source submission did not return a job ID")
        return self._submit_finalizer(state, spec, live_count)

    def _finalizer_passed(self, state: Mapping[str, Any], wave_id: str) -> bool:
        accounting = state["waves"][wave_id]["finalizer"].get("accounting")
        return bool(
            accounting
            and accounting.get("terminal_success") is True
            and accounting.get("contract_pass") is True
        )

    def _validate_prior_admission(
        self,
        *,
        wave_index: int,
        path: Path,
        expected_sha256: str,
    ) -> dict[str, str]:
        _validate_pin(expected_sha256, SHA256_RE, "prior admission SHA-256")
        resolved = _regular_path(self.root, path, "prior wave admission")
        expected_parent = (
            self.root
            / "results/corpus_v4/cps_reference_v2/production/v1/waves/r3"
        ).resolve()
        if expected_parent not in resolved.parents or resolved.name != "FINAL_ADMISSION.json":
            raise ControllerError("prior admission is outside the canonical R3 namespace")
        if sha256_file(resolved) != expected_sha256:
            raise ControllerError("prior admission SHA-256 differs")
        receipt = _load_json_object(resolved, "prior wave admission")
        roots = receipt.get("roots", {})
        decision = receipt.get("decision", {})
        if (
            receipt.get("schema")
            != "pcb-gnn.corpus-v4-fem-v2-production-wave-admission.v1"
            or receipt.get("artifact_stage") != "postterminal_wave_admission"
            or receipt.get("admission_eligible") is not True
            or receipt.get("fidelity_id") != "cps_fem_r3_p16_t1_v2"
            or receipt.get("wave_id") != wave_index - 1
            or roots.get("protocol_sha256") != self.config.protocol_sha256
            or roots.get("plan_sha256") != self.config.plan_sha256
            or roots.get("execution_lock_sha256") != self.config.lock_sha256
            or roots.get("source_git_head") != self.config.source_commit
            or decision.get("terminal_negative") is not False
            or decision.get("scientific_outcome") != "INDETERMINATE"
            or decision.get("retry_may_start") is not True
        ):
            raise ControllerError("prior admission does not authorize the next R3 shard")
        return {
            "path": resolved.relative_to(self.root).as_posix(),
            "sha256": expected_sha256,
        }

    def _apply_release(
        self,
        state: dict[str, Any],
        release_r3_through: int | None,
        prior_admission: Path | None,
        prior_admission_sha256: str | None,
    ) -> None:
        if release_r3_through is None:
            if prior_admission is not None or prior_admission_sha256 is not None:
                raise ControllerError("prior admission requires --release-r3-through")
            return
        current = state["releases"]["r3_through"]
        if release_r3_through == current:
            if prior_admission is not None or prior_admission_sha256 is not None:
                raise ControllerError("unchanged release must not replace an admission")
            return
        if release_r3_through != current + 1 or release_r3_through not in range(4):
            raise ControllerError("R3 waves must be released monotonically, one at a time")
        predecessor = f"r3_{release_r3_through - 1:03d}"
        if not self._finalizer_passed(state, predecessor):
            raise ControllerError("prior R3 finalizer is not terminal and successful")
        if prior_admission is None or prior_admission_sha256 is None:
            raise ControllerError("next R3 shard requires the prior postterminal admission")
        binding = self._validate_prior_admission(
            wave_index=release_r3_through,
            path=prior_admission,
            expected_sha256=prior_admission_sha256,
        )
        state["releases"]["r3_through"] = release_r3_through
        state["releases"]["prior_admissions"][str(release_r3_through)] = binding
        state["releases"]["events"].append(
            {
                "prior_admission": binding,
                "note": "manual scheduling release bound to a postterminal scientific admission",
                "released_r3_through": release_r3_through,
                "type": "operator_release",
                "utc": self._timestamp(),
            }
        )

    def _r3_candidate(self, state: Mapping[str, Any]) -> WaveSpec | None:
        released = int(state["releases"]["r3_through"])
        for spec in self.specs:
            if spec.r3_index is None or spec.r3_index > released:
                continue
            source = state["waves"][spec.wave_id]["source"]
            if source.get("job_id") is not None or source.get("status") in {
                "SUBMITTING",
                "SUBMISSION_AMBIGUOUS",
                "SUBMISSION_FAILED",
            }:
                continue
            if spec.r3_index > 0 and not self._finalizer_passed(
                state, f"r3_{spec.r3_index - 1:03d}"
            ):
                return None
            return spec
        return None

    def _missing_finalizers(self, state: Mapping[str, Any]) -> list[WaveSpec]:
        missing: list[WaveSpec] = []
        for spec in self.specs:
            wave = state["waves"][spec.wave_id]
            finalizer = wave["finalizer"]
            if wave["source"].get("job_id") and finalizer.get("job_id") is None:
                if finalizer.get("status") not in {
                    "SUBMITTING",
                    "SUBMISSION_AMBIGUOUS",
                    "SUBMISSION_FAILED",
                }:
                    missing.append(spec)
        return missing

    def _preview(
        self, state: Mapping[str, Any], assumed_live_count: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if assumed_live_count < 0:
            raise ControllerError("assumed live count cannot be negative")
        virtual_live = assumed_live_count
        actions: list[dict[str, Any]] = []

        r4 = self.by_id["r4_000"]
        if state["waves"]["r4_000"]["source"].get("job_id") is None:
            decision = self._capacity_decision(virtual_live, r4.expected_tasks + 1)
            if decision["allowed"]:
                actions.extend(
                    (
                        {"command": self._source_command(r4), "kind": "source", "wave_id": r4.wave_id},
                        {
                            "command": self._finalizer_command(
                                state, r4, "<SOURCE_JOB_ID>"
                            ),
                            "kind": "finalizer",
                            "wave_id": r4.wave_id,
                        },
                    )
                )
                virtual_live += r4.expected_tasks + 1
            else:
                actions.append({"capacity": decision, "kind": "blocked", "wave_id": r4.wave_id})

        candidate = self._r3_candidate(state)
        if candidate is not None:
            decision = self._capacity_decision(
                virtual_live, candidate.expected_tasks + 1
            )
            if decision["allowed"]:
                actions.extend(
                    (
                        {
                            "command": self._source_command(candidate),
                            "kind": "source",
                            "wave_id": candidate.wave_id,
                        },
                        {
                            "command": self._finalizer_command(
                                state, candidate, "<SOURCE_JOB_ID>"
                            ),
                            "kind": "finalizer",
                            "wave_id": candidate.wave_id,
                        },
                    )
                )
                virtual_live += candidate.expected_tasks + 1
            else:
                actions.append(
                    {"capacity": decision, "kind": "blocked", "wave_id": candidate.wave_id}
                )
        return actions, {
            "assumed_live_expanded_elements": assumed_live_count,
            "projected_live_expanded_elements": virtual_live,
        }

    def tick(
        self,
        *,
        release_r3_through: int | None = None,
        prior_admission: Path | None = None,
        prior_admission_sha256: str | None = None,
        dry_run: bool = False,
        assumed_live_count: int = 0,
    ) -> dict[str, Any]:
        """Advance one controller poll without ever invoking an admission tool."""

        with self._state_lock():
            state = self._load_state()
            if dry_run:
                self._apply_release(
                    state,
                    release_r3_through,
                    prior_admission,
                    prior_admission_sha256,
                )
                actions, capacity = self._preview(state, assumed_live_count)
                state["last_dry_run"] = {
                    "actions": actions,
                    "capacity": capacity,
                    "utc": self._timestamp(),
                }
                state["last_tick_utc"] = self._timestamp()
                self._save_state(state)
                return state

            live_identifiers, snapshot = self._squeue_snapshot()
            state["capacity"]["last_squeue"] = snapshot
            self._refresh_accounting(state, live_identifiers)
            # Refresh first so an operator can release the next wave in the
            # same invocation that observes the predecessor's terminal row.
            self._apply_release(
                state,
                release_r3_through,
                prior_admission,
                prior_admission_sha256,
            )
            live_count = len(live_identifiers)

            for spec in self._missing_finalizers(state):
                live_count = self._submit_finalizer(state, spec, live_count)

            r4 = self.by_id["r4_000"]
            r4_source = state["waves"][r4.wave_id]["source"]
            if r4_source.get("job_id") is None and r4_source.get("status") not in {
                "SUBMITTING",
                "SUBMISSION_AMBIGUOUS",
                "SUBMISSION_FAILED",
            }:
                live_count = self._submit_wave_pair(state, r4, live_count)

            if state["waves"]["r4_000"]["finalizer"].get("job_id") is not None:
                candidate = self._r3_candidate(state)
                if candidate is not None:
                    live_count = self._submit_wave_pair(state, candidate, live_count)

            state["capacity"]["projected_after_tick"] = live_count
            state["last_tick_utc"] = self._timestamp()
            self._save_state(state)
            return state


def _parse_extra_exports(values: Sequence[str]) -> dict[str, str]:
    exports: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ControllerError("--export requires NAME=VALUE")
        name, value = item.split("=", 1)
        if name in exports:
            raise ControllerError(f"duplicate --export variable: {name}")
        exports[name] = value
    _validate_export_map(exports)
    return exports


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--execution-root", type=Path, default=ROOT)
    result.add_argument("--state", type=Path, default=Path(STATE_RELATIVE))
    result.add_argument("--source-commit", required=True)
    result.add_argument("--protocol-sha256", required=True)
    result.add_argument("--plan-sha256", required=True)
    result.add_argument("--lock-sha256", required=True)
    result.add_argument(
        "--finalizer-script", type=Path, default=Path(FINALIZER_WRAPPER_RELATIVE)
    )
    result.add_argument("--username", default=getpass.getuser())
    result.add_argument("--release-r3-through", type=int, choices=range(4))
    result.add_argument("--prior-admission", type=Path)
    result.add_argument("--expected-prior-admission-sha256")
    result.add_argument("--export", action="append", default=[], metavar="NAME=VALUE")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--assume-live-elements", type=int, default=0)
    result.add_argument("--watch", action="store_true")
    result.add_argument("--poll-seconds", type=float, default=60.0)
    return result


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.poll_seconds <= 0:
        raise SystemExit("--poll-seconds must be positive")
    config = ControllerConfig(
        execution_root=args.execution_root,
        state_path=args.state,
        source_commit=args.source_commit,
        protocol_sha256=args.protocol_sha256,
        plan_sha256=args.plan_sha256,
        lock_sha256=args.lock_sha256,
        username=args.username,
        finalizer_script=args.finalizer_script,
        extra_exports=_parse_extra_exports(args.export),
    )
    controller = FemV2Controller(config, SubprocessRunner())
    release = args.release_r3_through
    while True:
        state = controller.tick(
            release_r3_through=release,
            prior_admission=args.prior_admission if release is not None else None,
            prior_admission_sha256=(
                args.expected_prior_admission_sha256 if release is not None else None
            ),
            dry_run=args.dry_run,
            assumed_live_count=args.assume_live_elements,
        )
        print(
            json.dumps(
                {
                    "last_tick_utc": state["last_tick_utc"],
                    "operator_admission_required": state["operator_admission_required"],
                    "releases": state["releases"],
                    "state": str(controller.state_path),
                    "waves": {
                        name: {
                            "finalizer": value["finalizer"]["status"],
                            "source": value["source"]["status"],
                        }
                        for name, value in state["waves"].items()
                    },
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        if args.dry_run or not args.watch:
            break
        release = None
        args.prior_admission = None
        args.expected_prior_admission_sha256 = None
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
