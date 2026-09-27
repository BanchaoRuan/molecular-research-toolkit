#!/usr/bin/env python3
"""Inspect no_G298 evidence; optionally prepare one independent retry batch.

Inspection is read-only. --prepare requires confirmation and never submits jobs.
Original inputs, logs, results and submission records are never rewritten.
"""

import argparse
import csv
import fcntl
import hashlib
import json
import math
import re
import shlex
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

sys.dont_write_bytecode = True

from extract_G298_batch import extract_g298_from_text, resolve_method_paths
from make_com import build_state_specs, read_molecules_from_smi, read_state_selection
from make_slurm import write_slurm_files, write_submit_script


ELEMENTS = (
    "X H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn "
    "Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd "
    "Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac "
    "Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
).split()
METRICS = ("Maximum Force", "RMS Force", "Maximum Displacement", "RMS Displacement")
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][-+]?\d+)?"
SCF = re.compile(r"SCF Done:\s+E\(([^)]+)\)\s*=\s*(" + NUMBER + r")\s+A\.U\. after\s+(\d+) cycles")
METRIC = re.compile(r"^\s*((?:Maximum|RMS)\s+(?:Force|Displacement))\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(YES|NO)\s*$")
DASH = re.compile(r"\s*-{10,}\s*")
SCF_FAILURE = "Convergence failure -- run terminated."
SPECIAL_ERRORS = {
    "pcm_matrix_failure": "Inv3 failed in PCMMkU",
    "cphf_failure": "CPHF failed to converge",
    "unsupported_basis": "Atomic number out of range for",
}
TERMINAL_STATES = {
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED", "NODE_FAIL",
    "OUT_OF_MEMORY", "PREEMPTED", "TIMEOUT", "REVOKED",
}


def number(value):
    result = float(value.rstrip(".").replace("D", "E").replace("d", "e"))
    if not math.isfinite(result):
        raise ValueError("Non-finite numeric evidence")
    return result


def regular_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return path


def sha256(path):
    return hashlib.sha256(regular_file(path).read_bytes()).hexdigest()


def orientation(lines, index):
    """Read a complete orientation table; indices and evidence lines are 1-based."""
    separators = [i for i in range(index + 1, min(index + 8, len(lines)))
                  if DASH.fullmatch(lines[i])][:2]
    if len(separators) != 2:
        raise ValueError(f"Invalid orientation header at line {index + 1}")
    atoms = []
    for i in range(separators[1] + 1, len(lines)):
        if DASH.fullmatch(lines[i]):
            if not atoms:
                raise ValueError("Empty orientation table")
            return {"line": index + 1, "atom_start_line": separators[1] + 2,
                    "end_line": i + 1, "atoms": atoms}
        fields = lines[i].split()
        if len(fields) != 6 or int(fields[0]) != len(atoms) + 1:
            raise ValueError(f"Invalid orientation row at line {i + 1}")
        atomic_number = int(fields[1])
        if not 0 < atomic_number < len(ELEMENTS) or int(fields[2]) != 0:
            raise ValueError(f"Unsupported atom at line {i + 1}")
        for value in fields[3:]:
            number(value)
        atoms.append([ELEMENTS[atomic_number], *fields[3:]])
    raise ValueError("Truncated orientation table")


def density_evidence(lines, geometry, scf_line):
    patterns = {
        "required_rms": re.compile(r"Requested convergence on RMS density matrix=\s*(\S+)"),
        "required_max": re.compile(r"Requested convergence on MAX density matrix=\s*(\S+)"),
        "actual": re.compile(r"RMSDP=\s*(\S+)\s+MaxDP=\s*(\S+)"),
    }
    result = {}
    for line in lines[geometry["end_line"] - 1:scf_line]:
        for name, pattern in patterns.items():
            match = pattern.search(line)
            if match:
                if name == "actual":
                    result.update(observed_rms=number(match[1]), observed_max=number(match[2]))
                else:
                    result[name] = number(match[1])
    complete = len(result) == 4
    result["pass"] = complete and all(
        result["required_" + metric] > 0
        and 0 <= result["observed_" + metric] <= result["required_" + metric]
        for metric in ("rms", "max")
    )
    if not complete:
        result["reason"] = "Missing printed density-convergence evidence"
    return result


def route_from_lines(lines):
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            raw = []
            for row in lines[i:]:
                if DASH.fullmatch(row):
                    return {"line": i + 1, "text": "".join(raw).strip()}
                raw.append(row[1:] if row.startswith(" ") else row)
            raise ValueError("Truncated Gaussian route section")
    return None


def geometry_difference(first, second):
    """Pair-distance comparison is invariant to rigid translation and rotation."""
    if [a[0] for a in first] != [a[0] for a in second]:
        raise ValueError("Geometry atom count or ordered elements differ")
    a = [[number(v) for v in atom[1:]] for atom in first]
    b = [[number(v) for v in atom[1:]] for atom in second]
    return max((abs(math.dist(a[i], a[j]) - math.dist(b[i], b[j]))
                for i in range(len(a)) for j in range(i)), default=0.0)


def parse_log(text):
    """Bind each valid SCF/metric evaluation to its own complete geometry.

    SCF Done alone does not establish SCF convergence. Incomplete tables, failed
    density convergence and repeated/ambiguous evaluations are not candidates.
    A new optimization sequence is kept separate from earlier sequences.
    """
    lines = text.splitlines()
    records, rejected, faults, terminations, completed = [], [], [], [], []
    geometry = input_geometry = scf = step = None
    previous_metric_line = 0
    sequence = 1
    last_step = None
    used_scf = set()
    last_record = None
    orientations = []
    for i, line in enumerate(lines):
        if "Entering Gaussian System" in line and i > 1:
            sequence += 1
            geometry = input_geometry = scf = step = last_record = None
            last_step = None
            previous_metric_line = i + 1
        for kind, pattern in SPECIAL_ERRORS.items():
            if pattern in line:
                faults.append({"kind": kind, "line": i + 1, "text": line.strip()})
        if SCF_FAILURE in line:
            faults.append({"kind": "scf_failure", "line": i + 1, "text": line.strip()})
            scf = None
        if "Error termination" in line or "Normal termination" in line:
            terminations.append({"line": i + 1, "text": line.strip()})
            scf = geometry = input_geometry = None
        if "Standard orientation:" in line or "Input orientation:" in line:
            try:
                parsed = orientation(lines, i)
            except (ValueError, IndexError) as error:
                rejected.append({"line": i + 1, "reason": str(error)})
                geometry = scf = None
                continue
            if "Input orientation:" in line:
                input_geometry = parsed
            parsed["kind"] = "standard" if "Standard orientation:" in line else "input"
            orientations.append(parsed)
            geometry = parsed
            scf = None
        match = SCF.search(line)
        if match:
            scf = {"line": i + 1, "energy_hartree": number(match[2]),
                   "energy_printed": match[2], "scf_method": match[1],
                   "cycles": int(match[3]), "geometry": geometry,
                   "input_orientation_line": input_geometry["line"] if input_geometry else None}
        match = re.search(r"Step number\s+(\d+)\s+out of a maximum of\s+(\d+)", line)
        if match:
            step = int(match[1])
            if last_step is not None and step <= last_step:
                sequence += 1
                last_record = None
            last_step = step
        if "Maximum Force" in line:
            last_record = None
            rows = [METRIC.fullmatch(row) for row in lines[i:i + 4]]
            if len(rows) != 4 or not all(rows):
                rejected.append({"line": i + 1, "reason": "Incomplete four-metric table"})
                scf = None
                continue
            if tuple(" ".join(row[1].split()) for row in rows) != METRICS:
                continue
            if (not scf or step is None or scf["geometry"] is None
                    or scf["line"] in used_scf):
                rejected.append({"line": i + 1, "reason": "No unique SCF/geometry evaluation for metrics"})
                continue
            geom = scf["geometry"]
            try:
                values = [number(row[2]) for row in rows]
                thresholds = [number(row[3]) for row in rows]
                if min(values) < 0 or min(thresholds) <= 0:
                    raise ValueError("Invalid convergence metrics")
                if not previous_metric_line < geom["line"] < geom["end_line"] < scf["line"] < i + 1:
                    raise ValueError("Geometry/SCF/metrics are not a complete ordered evaluation")
                density = density_evidence(lines, geom, scf["line"])
                if not density["pass"]:
                    raise ValueError(density.get("reason", "Printed SCF density thresholds not met"))
                ratios = [v / t for v, t in zip(values, thresholds)]
                if not all(math.isfinite(ratio) for ratio in ratios):
                    raise ValueError("Non-finite convergence ratio")
                record = {k: v for k, v in scf.items() if k != "geometry"}
                record.update(step=step, sequence=sequence, convergence_line=i + 1,
                              orientation_line=geom["line"], geometry=geom,
                              values=values, thresholds=thresholds,
                              passed=[row[4] == "YES" for row in rows],
                              ratios=ratios, score=max(ratios),
                              scf_density_convergence=density)
                records.append(record)
                last_record = record
                used_scf.add(scf["line"])
            except ValueError as error:
                rejected.append({"line": i + 1, "reason": str(error)})
            previous_metric_line = i + 1
        if "Optimization completed" in line:
            if last_record and last_record["sequence"] == sequence:
                completed.append({"line": i + 1, "record_line": last_record["convergence_line"],
                                  "sequence": sequence})
            else:
                rejected.append({"line": i + 1, "reason": "Optimization completion has no associated valid point"})
    for completion in completed:
        point = next(r for r in records if r["convergence_line"] == completion["record_line"])
        stop = min([t["line"] for t in terminations if t["line"] > completion["line"]]
                   + [i + 1 for i, row in enumerate(lines)
                      if i + 1 > completion["line"] and row.lstrip().startswith("#")]
                   + [len(lines) + 1])
        following = [g for g in orientations if completion["line"] < g["line"] < stop
                     and g["kind"] == "standard"]
        final_geometry = following[-1] if following else point["geometry"]
        try:
            delta = geometry_difference(point["geometry"]["atoms"], final_geometry["atoms"])
            # Retain the tolerance used in the reviewed completed-OPT package.
            if delta >= 0.00003:
                raise ValueError("Completed geometry differs from its evaluated optimization point")
            completion.update(geometry=final_geometry, pair_distance_max_delta_angstrom=delta)
        except ValueError as error:
            completion["geometry_error"] = str(error)
    charge_pairs = sorted({(int(q), int(m)) for q, m in re.findall(
        r"Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)", text)})
    counts = sorted({int(n) for n in re.findall(r"NAtoms=\s*(\d+)", text)})
    return {"records": records, "rejected_evaluations": rejected,
            "faults": faults, "terminations": terminations, "completed": completed,
            "charge_multiplicity": charge_pairs, "atom_counts": counts,
            "route": route_from_lines(lines), "sequence_count": sequence,
            "has_g298": extract_g298_from_text(text) is not None}


def classify_evidence(evidence):
    if evidence["has_g298"]:
        return {"status": "not_no_G298", "reason": "G298 is already present"}
    special = [f for f in evidence["faults"] if f["kind"] in SPECIAL_ERRORS]
    if special:
        return {"status": "other_fault", "reason": ", ".join(f["kind"] for f in special)}
    if not evidence["records"]:
        return {"status": "manual", "reason": "No complete valid optimization evaluation"}
    if evidence["sequence_count"] != 1:
        return {"status": "manual", "reason": "Multiple optimization sequences require explicit source association"}
    if evidence["completed"]:
        completion = evidence["completed"][-1]
        if completion.get("geometry_error"):
            return {"status": "manual", "reason": completion["geometry_error"]}
        line = completion["record_line"]
        selected = next(r for r in evidence["records"] if r["convergence_line"] == line)
        return {"status": "candidate", "reason": "Gaussian explicitly announced optimization completion",
                "selected": selected, "coordinates": completion["geometry"],
                "policy": "optimization_completed"}
    if len(evidence["records"]) == 1:
        return {"status": "candidate", "reason": "Evaluated initial geometry; not an improved geometry",
                "selected": evidence["records"][0], "coordinates": evidence["records"][0].get("geometry"),
                "policy": "only_valid"}
    selected, policy, detail = select_trajectory(evidence["records"])
    if selected is None:
        return {"status": "manual", "reason": "No reliable trajectory candidate", "policy": policy}
    return {"status": "candidate", "selected": selected, "coordinates": selected["geometry"],
            "policy": policy, "reason": policy.replace("_", " "), "selection_evidence": detail}


def select_trajectory(records):
    """Rank complete evaluations, not raw optimizer steps or SCF energies alone.

    Ratios use each point's printed Gaussian thresholds. Recurrence tolerances
    reflect printed precision, not convergence criteria. Historical candidates
    are explicitly labelled; they are not assertions of a unique cycle onset.
    """
    def rank(point):
        return point["score"], point["energy_hartree"], -point["step"]

    def force(point):
        return math.sqrt(point["ratios"][0] * point["ratios"][1])

    def phase(block, field):
        values = [p["energy_hartree"] if field == 0 else p["values"][field - 1] for p in block]
        return tuple(sorted(range(len(block)), key=lambda i: values[i]))

    if not records:
        return None, "no_valid_point", {}
    if len(records) == 1:
        return records[0], "only_valid", {}
    first = records[0]
    if all(abs(p["energy_hartree"] - first["energy_hartree"]) <= 1.01e-8
           and all(abs(a - b) <= 1.01e-6 for a, b in zip(p["values"], first["values"]))
           and geometry_difference(p["geometry"]["atoms"], first["geometry"]["atoms"]) < 3e-5
           for p in records[1:]):
        return None, "stationary_without_improvement_evidence", {}
    for period in range(2, len(records) // 2 + 1):
        before, after = records[-2 * period:-period], records[-period:]
        if not all(abs(a["energy_hartree"] - b["energy_hartree"]) <= 1.01e-8
                   and all(abs(x - y) <= 1.01e-6 for x, y in zip(a["values"], b["values"]))
                   and geometry_difference(a["geometry"]["atoms"], b["geometry"]["atoms"]) < 3e-5
                   for a, b in zip(before, after)):
            continue
        if max(p["energy_hartree"] for p in after) - min(p["energy_hartree"] for p in after) <= 1.01e-8:
            continue  # Stationary evidence is not a multipoint oscillation.
        start = len(records) - 2 * period
        template = [phase(after, field) for field in range(5)]
        excursion = max(geometry_difference(a["geometry"]["atoms"], b["geometry"]["atoms"])
                        for a in after for b in after)
        while start >= period:
            block = records[start - period:start]
            if (sum(phase(block, f) == template[f] for f in range(5)) < 4
                    or any(geometry_difference(a["geometry"]["atoms"], b["geometry"]["atoms"])
                           > max(excursion, 3e-5) for a, b in zip(block, after))):
                break
            start -= period
        if start:
            return min(records[:start], key=rank), "pre_cycle_region", {
                "period": period, "candidate_end": records[start - 1]["step"],
                "recurrence": "energy, four metrics and pair distances",
                "region": "backtracked phase-consistent region; not a proven unique onset"}
        return None, "cycle_without_reliable_prefix", {"period": period}
    last, previous = records[-1], records[-2]
    historical = min(records, key=rank)
    rebound = last["energy_hartree"] > previous["energy_hartree"] and force(last) > force(previous)
    if (rebound and historical is records[0]
            and previous["energy_hartree"] < historical["energy_hartree"]
            and force(previous) < force(historical)):
        return previous, "before_rebound_after_relaxation", {}
    # A force-converged lower-energy endpoint can supersede a historical score
    # minimum. 1 microhartree is a ranking tolerance, not a Gaussian threshold.
    progressed = (all(r <= 1 for r in last["ratios"][:2])
                  and last["energy_hartree"] < historical["energy_hartree"] - 1e-6)
    if force(historical) < force(last) and not progressed:
        return historical, "historical_candidate", {"candidate_end": last["step"]}
    if rebound:
        return previous, "before_energy_force_rebound", {}
    if all(a > b for a, b in zip(last["values"], previous["values"])):
        return previous, "before_four_metric_deterioration", {}
    if last["energy_hartree"] <= previous["energy_hartree"]:
        return last, "latest_evaluated", {}
    return None, "conflicting_trend", {}


def recorded_job_id(method, molecule_id, state):
    path = method / "submit" / "submitted.tsv"
    if not path.exists() and not path.is_symlink():
        return None
    with regular_file(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["molecule_id", "state", "slurm_path", "job_id"]:
            raise ValueError(f"Invalid submission record header: {path}")
        rows = [r for r in reader if r["molecule_id"] == molecule_id and r["state"] == state]
    if len(rows) > 1:
        raise ValueError(f"Ambiguous job ID for {molecule_id}/{state}")
    if not rows:
        return None
    row = rows[0]
    if not re.fullmatch(r"\d+(?:;[A-Za-z0-9_.-]+)?", row["job_id"]):
        raise ValueError(f"Invalid recorded job ID: {row['job_id']}")
    expected = method / "work" / molecule_id / f"{state}.slurm"
    # Relocated task copies are not matched to an unrelated local scheduler job.
    if Path(row["slurm_path"]) != expected:
        return None
    return row["job_id"]


def run_scheduler(arguments):
    try:
        result = subprocess.run(arguments, text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if result.returncode:
        return None, result.stderr.strip() or f"Exit {result.returncode}"
    return result.stdout, None


def lifecycle(job_id, logs_finished=False, runner=run_scheduler, which=shutil.which):
    """An empty queue is never terminal proof; a known live job cannot be overridden."""
    evidence = []
    if job_id and which("squeue"):
        job, _, cluster = job_id.partition(";")
        arguments = ["squeue", "--noheader", "--jobs", job, "--format=%i|%T"]
        if cluster:
            arguments.extend(["--clusters", cluster])
        output, error = runner(arguments)
        evidence.append({"command": arguments, "output": output, "error": error})
        if output is not None:
            entries = [s.strip() for s in output.splitlines() if s.strip() and not s.startswith("CLUSTER:")]
            # Any queue entry, including unfamiliar transitional states, is held.
            if entries:
                return {"status": "wait", "reason": "Job is still present in the queue", "evidence": evidence}
        if output is not None and which("sacct"):
            arguments = ["sacct", "--noheader", "--parsable2", "--allocations",
                         "--jobs", job, "--format=JobIDRaw,State"]
            if cluster:
                arguments.extend(["--clusters", cluster])
            output, error = runner(arguments)
            evidence.append({"command": arguments, "output": output, "error": error})
            rows = [row.split("|") for row in (output or "").splitlines() if row.strip()]
            matches = [row for row in rows if len(row) >= 2 and row[0].strip() == job]
            if len(matches) == 1 and matches[0][1].strip():
                state = matches[0][1].strip().split()[0].rstrip("+")
                if state in TERMINAL_STATES:
                    return {"status": "finished", "reason": f"Accounting state: {state}", "evidence": evidence}
                return {"status": "wait", "reason": f"Accounting state is not terminal: {state}", "evidence": evidence}
    if logs_finished:
        return {"status": "finished", "reason": "User attested that source logs are from finished jobs",
                "evidence": evidence, "user_attestation": True}
    return {"status": "unknown", "reason": "No reliable terminal state; do not infer completion from no_G298",
            "evidence": evidence}


def normalized_route(route):
    return re.sub(r"\s+", "", route).lower()


def saved_parameters(method):
    text = regular_file(method / "preparation.log").read_text(encoding="utf-8")
    parameters = {}
    for name in ("Functional", "Basis set", "Solvation model", "Route keywords",
                 "CPU cores", "Nodes", "Tasks", "Partition", "Walltime"):
        rows = [line[len(name) + 2:] for line in text.splitlines() if line.startswith(name + ": ")]
        if len(rows) != 1 or not rows[0]:
            raise ValueError(f"Missing or ambiguous saved {name}; source parameters need manual review")
        parameters[name] = rows[0]
    for name, label in zip(("Functional", "Basis set", "Solvation model"), method.name.split("__")):
        if not parameters[name].startswith(label + " -> "):
            raise ValueError(f"Saved {name} does not match the method directory")
    return parameters


def source_input(method, molecule, spec, evidence, decision, parameters):
    """Accept only self-contained Cartesian inputs with unambiguous provenance."""
    state, mid = spec["state"], molecule["molecule_id"]
    com = method / "work" / mid / f"{state}.com"
    slurm = com.with_suffix(".slurm")
    lines = regular_file(com).read_text(encoding="utf-8").splitlines()
    headers, index = {}, 0
    while index < len(lines) and lines[index].startswith("%"):
        key, separator, value = lines[index][1:].partition("=")
        key = key.lower()
        if not separator or key in headers or key not in {"nprocshared", "mem", "chk"}:
            raise ValueError("Unsupported or duplicate COM Link 0 directive")
        headers[key] = value.strip()
        index += 1
    if set(headers) != {"nprocshared", "mem", "chk"}:
        raise ValueError("COM lacks its resource/checkpoint directives")
    sections = re.split(r"\n\s*\n", "\n".join(lines[index:]).strip())
    if len(sections) != 3 or not sections[0].startswith("#"):
        raise ValueError("COM is not a single self-contained Cartesian job")
    route, title, body = sections
    if re.search(r"\b(?:geom|gen|genecp|chkbasis|modredundant|restart)\b|guess\s*=\s*(?:\([^)]*)?read", route, re.I):
        raise ValueError("COM requires external geometry, basis, checkpoint or restart data")
    body = body.splitlines()
    if body[0].split() != [str(spec["charge"]), str(spec["multiplicity"])]:
        raise ValueError("COM charge/multiplicity differs from the saved state")
    atoms = [row.split() for row in body[1:]]
    for atom in atoms:
        if len(atom) != 4 or atom[0] not in ELEMENTS[1:]:
            raise ValueError("COM contains unsupported coordinates or extra input sections")
        for value in atom[1:]:
            number(value)
    selected_atoms = decision["coordinates"]["atoms"]
    if [a[0] for a in atoms] != [a[0] for a in selected_atoms]:
        raise ValueError("Log atom order/composition differs from the source COM")
    if evidence["atom_counts"] != [len(atoms)]:
        raise ValueError("Log atom-count evidence is missing or ambiguous")
    if not evidence["route"] or normalized_route(evidence["route"]["text"]) != normalized_route(route):
        raise ValueError("Log route differs from the source COM")
    functional = parameters["Functional"].split(" -> ", 1)[1]
    basis = parameters["Basis set"].split(" -> ", 1)[1]
    solvation = parameters["Solvation model"].split(" -> ", 1)[1]
    if solvation.count("{solvent}") != 1:
        raise ValueError("Saved solvation route lacks a unique solvent placeholder")
    expected = f"#p {parameters['Route keywords']} {functional}/{basis} {solvation.replace('{solvent}', molecule['solvent'])}"
    if normalized_route(route) != normalized_route(expected):
        raise ValueError("COM method/solvent/route differs from the saved preparation")
    if (not re.fullmatch(r"[1-9]\d*", headers["nprocshared"])
            or headers["nprocshared"] != parameters["CPU cores"]
            or not re.fullmatch(r"[1-9]\d*(?:KB|MB|GB|TB|KW|MW|GW|TW)", headers["mem"], re.I)):
        raise ValueError("COM resources are invalid or inconsistent with preparation")
    directives = {}
    for line in regular_file(slurm).read_text(encoding="utf-8").splitlines():
        if line.startswith("#SBATCH "):
            key, _, value = line[8:].replace("=", " ", 1).partition(" ")
            if key in directives:
                raise ValueError("Duplicate Slurm directive")
            directives[key] = value.strip()
    if set(directives) != {"-J", "-o", "-e", "-D", "-N", "-p", "--ntasks", "--cpus-per-task", "-t"}:
        raise ValueError("Source Slurm has unsupported or missing directives; review custom settings manually")
    expected_resources = {"-N": parameters["Nodes"], "--ntasks": parameters["Tasks"],
                          "--cpus-per-task": headers["nprocshared"], "-p": parameters["Partition"],
                          "-t": parameters["Walltime"].split(" -> ")[-1]}
    if any(directives[key] != value for key, value in expected_resources.items()):
        raise ValueError("Slurm resources differ from the recorded preparation")
    return {"route": route, "title": title, "headers": headers,
            "nodes": int(directives["-N"]), "ntasks": int(directives["--ntasks"]),
            "cpu_cores": int(headers["nprocshared"]), "partition": directives["-p"],
            "walltime": directives["-t"], "source_com": str(com), "source_slurm": str(slurm)}


def babel_convert(text, input_format, add_hydrogens=False):
    arguments = [f"-i{input_format}", "-omol"] + (["-h"] if add_hydrogens else [])
    if shutil.which("obabel"):
        command = ["obabel", *arguments]
    else:
        # Reuse the module already required by normal preparation. No install,
        # optimization, conformer search or 3D generation is performed here.
        command = ["bash", "-c",
                   'set +e; set +u; set +o pipefail; module load openbabel/3.1.1-gcc14.2.0 >&2 || exit; exec obabel "$@"',
                   "recovery", *arguments]
    try:
        result = subprocess.run(command, input=text, text=True, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Open Babel conversion unavailable: {error}") from error
    if result.returncode or "1 molecule converted" not in result.stderr:
        raise RuntimeError("Open Babel did not convert exactly one molecule: " + result.stderr.strip())
    return result.stdout


def mol_graph(text):
    lines = text.splitlines()
    if len(lines) < 4 or "V2000" not in lines[3]:
        raise ValueError("Open Babel did not produce a V2000 molecule")
    n, bonds = int(lines[3][:3]), int(lines[3][3:6])
    if n < 1 or len(lines) < 4 + n + bonds:
        raise ValueError("Incomplete molecular graph")
    elements = [line[31:34].strip() for line in lines[4:4 + n]]
    edges = [set() for _ in elements]
    for line in lines[4 + n:4 + n + bonds]:
        a, b = int(line[:3]) - 1, int(line[3:6]) - 1
        if not (0 <= a < n and 0 <= b < n) or a == b or b in edges[a]:
            raise ValueError("Invalid molecular graph bond")
        edges[a].add(b)
        edges[b].add(a)
    return elements, edges


def same_connectivity(first, second):
    """Element-labelled graph isomorphism, ignoring bond order/charge/stereo.

    Redox may change electronic structure. Connectivity is a safety check, not
    proof of stereochemistry or a chemically valid optimized minimum.
    """
    a, ae = first
    b, be = second
    labels_a = [(a[i], len(ae[i])) for i in range(len(a))]
    labels_b = [(b[i], len(be[i])) for i in range(len(b))]
    if Counter(labels_a) != Counter(labels_b):
        return False
    for _ in range(len(a)):
        new_a = [(labels_a[i], tuple(sorted(labels_a[j] for j in ae[i]))) for i in range(len(a))]
        new_b = [(labels_b[i], tuple(sorted(labels_b[j] for j in be[i]))) for i in range(len(b))]
        palette = {label: i for i, label in enumerate(sorted(set(new_a + new_b)))}
        next_a, next_b = [palette[x] for x in new_a], [palette[x] for x in new_b]
        if Counter(next_a) != Counter(next_b):
            return False
        stable = len(set(next_a)) == len(set(labels_a))
        labels_a, labels_b = next_a, next_b
        if stable:
            break
    mapping, used, visited = {}, set(), 0

    def match():
        nonlocal visited
        visited += 1
        if visited > 100000:
            raise ValueError("Molecular graph comparison exceeded its safe search bound")
        if len(mapping) == len(a):
            return True
        i = max((i for i in range(len(a)) if i not in mapping),
                key=lambda i: (sum(j in mapping for j in ae[i]), -labels_a.count(labels_a[i]), len(ae[i])))
        for j in range(len(b)):
            if j in used or labels_a[i] != labels_b[j]:
                continue
            if any((k in ae[i]) != (v in be[j]) for k, v in mapping.items()):
                continue
            mapping[i] = j
            used.add(j)
            if match():
                return True
            del mapping[i]
            used.remove(j)
        return False

    return match()


def validate_identity(molecule, spec, atoms, converter=babel_convert):
    xyz = f"{len(atoms)}\nRecovery connectivity check only\n" + "\n".join(" ".join(a) for a in atoms) + "\n"
    expected = mol_graph(converter(molecule["smiles"] + "\n", "smi", True))
    observed = mol_graph(converter(xyz, "xyz"))
    if Counter(expected[0]) != Counter(a[0] for a in atoms):
        raise ValueError("Candidate composition differs from the original SMILES with explicit hydrogens")
    if observed[0] != [a[0] for a in atoms] or not same_connectivity(expected, observed):
        raise ValueError("Candidate connectivity differs from the original SMILES")
    electrons = sum(ELEMENTS.index(a[0]) for a in atoms) - spec["charge"]
    if electrons < 0 or spec["multiplicity"] > electrons + 1 or (electrons - spec["multiplicity"] + 1) % 2:
        raise ValueError("Charge/multiplicity is inconsistent with the electron count")
    distances = [math.dist([number(v) for v in a[1:]], [number(v) for v in b[1:]])
                 for i, a in enumerate(atoms) for b in atoms[:i]]
    if distances and min(distances) < 0.3:
        raise ValueError("Candidate has overlapping or nearly coincident nuclei")
    return {"composition": "match", "connectivity": "match", "electron_parity": "pass",
            "minimum_pair_distance_angstrom": min(distances) if distances else None,
            "tool": "Open Babel; no coordinate generation", "stereochemistry": "not assessed"}


def retry_name(method, state):
    name = f"{method.parent.name}_{method.name}_{state}_retry"
    if len((name + ".smi").encode()) > 255:
        raise ValueError("Retry batch name exceeds the filesystem filename limit")
    return name


def provenance_job(case):
    selected = case["analysis"]["selected"]
    return {**{key: case[key] for key in ("molecule_id", "state", "molecule", "spec", "source_log",
                                         "source_log_sha256", "input", "identity", "lifecycle")},
            "selection": {"policy": case["analysis"]["policy"],
                          "orientation_line": case["analysis"]["coordinates"]["line"],
                          "region_evidence": case["analysis"].get("selection_evidence", {}),
                          **{key: value for key, value in selected.items() if key != "geometry"}}}


def check_source_snapshot(snapshot):
    for name, digest in snapshot.items():
        path = Path(name)
        actual = sha256(path) if path.exists() or path.is_symlink() else None
        if actual != digest:
            raise ValueError(f"Source changed during recovery; inspect again: {path}")


def check_runtime_paths(base, method, results):
    for path in (base / "inputs", base / "calculations", base / "results", method, results):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError(f"Runtime directory must not be a symlink or a file: {path}")
    for path in (method / "work", method / "submit", method / "logs"):
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"Source method directory must be a regular directory: {path}")


def prepare_retries(method, cases, options, parameters, snapshot, logs_finished):
    """Publish whole new batches only. A failed stage is retained, never merged."""
    base = method.parent.parent.parent
    check_runtime_paths(base, method, base / "results" / method.parent.name / method.name)
    groups = {o["label"]: [c for c in cases if c["state"] == o["label"] and c["status"] == "ready"]
              for o in options}
    groups = {state: group for state, group in groups.items() if group}
    if not groups:
        raise ValueError("No eligible jobs to prepare")
    names = {state: retry_name(method, state) for state in groups}

    def targets_free():
        for name in names.values():
            for path in (base / "inputs" / f"{name}.smi", base / "calculations" / name,
                         base / "results" / name, base / "calculations" / f".{name}.preparing"):
                if path.exists() or path.is_symlink():
                    raise ValueError(f"Retry already exists or has an interrupted stage; no overwrite: {path}")

    targets_free()
    print("\nIndependent retry preparation (no submission):")
    for state, group in groups.items():
        print(f"  {names[state]}: {len(group)} {state} job(s)")
        print(f"    method: {method.name}; source COM resources and route retained")
        for case in group:
            source = case["input"]
            print(f"    {case['molecule_id']}: {source['cpu_cores']} cores; "
                  f"{source['headers']['mem']}; {source['walltime']}; partition {source['partition']}")
    print("This fixes the retry subset permanently; excluded jobs cannot be appended later.")
    try:
        answer = input("Prepare these new batches? [y/N]: ").strip().lower()
    except EOFError:
        answer = ""
    if answer not in {"y", "yes"}:
        print("Cancelled; no files written.")
        return []
    lock_path = base / "calculations" / ".recovery.lock"
    if lock_path.is_symlink():
        raise ValueError("Recovery lock cannot be a symbolic link")
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another recovery preparation is active") from error
        targets_free()
        check_source_snapshot(snapshot)
        published, staged = [], []
        for state, group in groups.items():
            name = names[state]
            stage = base / "calculations" / f".{name}.preparing"
            stage.mkdir()
            task = stage / "task"
            output = task / method.name
            final = base / "calculations" / name / method.name
            result = base / "results" / name / method.name
            for directory in (task / "coordinates", output / "work", output / "logs", output / "submit", stage / "results" / method.name):
                directory.mkdir(parents=True, exist_ok=True)
            smi_text = "".join(f"{c['molecule']['smiles']} {c['molecule_id']} {c['molecule']['solvent']}\n" for c in group)
            (task / f"{name}.smi").write_text(smi_text, encoding="utf-8")
            option = next(o for o in options if o["label"] == state)
            prep_lines = ["Independent coordinate-based retry", f"Source method: {method}",
                          "Selected state parameters: " + json.dumps([option]),
                          *[f"{key}: {value}" for key, value in parameters.items()],
                          "Coordinates: selected source log -> COM; no XYZ output",
                          "No source results are overwritten or backfilled."]
            preparation = output / "preparation.log"
            preparation.write_text("\n".join(prep_lines) + "\n", encoding="utf-8")
            manifest = {"schema": "barkla-redox-retry-v1", "coordinate_source": "log_to_com",
                        "batch_input_sha256": sha256(task / f"{name}.smi"), "molecules": []}
            for case in group:
                mid, source = case["molecule_id"], case["input"]
                work = output / "work" / mid
                work.mkdir()
                (stage / "results" / method.name / mid).mkdir()
                atoms = case["analysis"]["coordinates"]["atoms"]
                text = "\n".join([f"%nprocshared={source['headers']['nprocshared']}",
                                  f"%mem={source['headers']['mem']}", f"%chk={result / mid / (state + '.chk')}",
                                  source["route"], "", source["title"], "",
                                  f"{case['spec']['charge']} {case['spec']['multiplicity']}",
                                  *(" ".join(atom) for atom in atoms), "", ""])
                (work / f"{state}.com").write_text(text, encoding="utf-8")
                with redirect_stdout(StringIO()):
                    write_slurm_files(mid, preparation, work, final / "work" / mid,
                                      result / mid, final / "logs", *method.name.split("__"),
                                      source["nodes"], source["ntasks"], source["cpu_cores"],
                                      source["partition"], source["walltime"])
                manifest["molecules"].append({"molecule_id": mid, "state": state,
                    "source_log_sha256": case["source_log_sha256"],
                    "orientation_line": case["analysis"]["coordinates"]["line"],
                    "step": case["analysis"]["selected"]["step"], "policy": case["analysis"]["policy"],
                    "com": f"{method.name}/work/{mid}/{state}.com", "com_sha256": sha256(work / f"{state}.com")})
            (task / "coordinates" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            with redirect_stdout(StringIO()):
                write_submit_script(output / "submit" / "submit.sh", [c["molecule_id"] for c in group], [state])
            provenance = {"schema": "barkla-redox-retry-v1", "source_method": str(method),
                          "created_utc": datetime.now(timezone.utc).isoformat(),
                          "source_sha256": snapshot, "jobs": [provenance_job(c) for c in group],
                          "scope": "One independent retry; no automatic source-result backfill"}
            (output / "retry_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
            staged.append((stage, name, smi_text))
        # Recheck both immutable inputs and live job state after potentially slow
        # graph checks / confirmation. Never rely on a stale extraction table.
        check_source_snapshot(snapshot)
        if (method / "submit" / ".submission.lock").exists():
            raise ValueError("Source submission is in progress; retry stages retained for review")
        for group in groups.values():
            for case in group:
                life = lifecycle(recorded_job_id(method, case["molecule_id"], case["state"]), logs_finished)
                if life["status"] != "finished":
                    raise ValueError("Source job is no longer confirmed finished; retry stages retained for review")
        check_source_snapshot(snapshot)
        for stage, name, smi_text in staged:
            check_runtime_paths(base, method, base / "results" / method.parent.name / method.name)
            for target in (base / "calculations" / name, base / "results" / name):
                if target.exists() or target.is_symlink():
                    raise ValueError(f"Retry target appeared during preparation: {target}")
            (base / "inputs").mkdir(exist_ok=True)
            # Publication is fail-closed: retain incomplete artifacts after an
            # interruption. A complete method is exposed only as the final step.
            with (base / "inputs" / f"{name}.smi").open("x", encoding="utf-8") as handle:
                handle.write(smi_text)
            (stage / "results").rename(base / "results" / name)
            (stage / "task").rename(base / "calculations" / name)
            stage.rmdir()  # This is our now-empty transaction directory only.
            published.append(base / "calculations" / name / method.name)
        return published


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calculation_method_directory")
    parser.add_argument("--state", help="A state label recorded in this task's preparation log")
    parser.add_argument("--ids", nargs="+", help="Inspect only these recorded molecule IDs")
    parser.add_argument("--logs-finished", action="store_true",
                        help="Attest that these source logs belong to finished jobs; never overrides a known live job")
    parser.add_argument("--json", action="store_true", help="Print read-only evidence as JSON")
    parser.add_argument("--prepare", action="store_true", help="Confirm and prepare independent retry batches; never submit")
    return parser.parse_args()


def main():
    args = parse_arguments()
    if args.prepare and args.json:
        raise ValueError("--json is read-only; use --prepare separately for interactive confirmation")
    method, smi, results = resolve_method_paths(args.calculation_method_directory)
    check_runtime_paths(method.parent.parent.parent, method, results)
    if (method.parent.name.endswith("_retry") or (method / "retry_provenance.json").exists()
            or (method / "retry_ready.json").exists()):
        raise ValueError("A retry batch is not eligible for another automatic retry")
    snapshot = {str(p): sha256(p) for p in (smi, method / "preparation.log")}
    molecules = read_molecules_from_smi(smi)
    options = read_state_selection(method / "preparation.log")
    if args.state and args.state not in {option["label"] for option in options}:
        raise ValueError("Requested state was not selected for this calculation method")
    if args.ids:
        if len(set(args.ids)) != len(args.ids) or set(args.ids) - {m["molecule_id"] for m in molecules}:
            raise ValueError("Requested molecule IDs contain duplicates or unknown IDs")
        molecules = [m for m in molecules if m["molecule_id"] in args.ids]
    if args.state:
        options = [o for o in options if o["label"] == args.state]
    parameters = None
    submitted = method / "submit" / "submitted.tsv"
    snapshot[str(submitted)] = sha256(submitted) if submitted.exists() or submitted.is_symlink() else None
    cases = []
    for molecule in molecules:
        mid = molecule["molecule_id"]
        for spec in build_state_specs(molecule["base_charge"], options):
            state = spec["state"]
            path = results / mid / f"{state}.log"
            for parent in (results.parent, results / mid, method / "work" / mid):
                if parent.is_symlink():
                    raise ValueError(f"Source directory cannot be a symbolic link: {parent}")
            case = {"molecule_id": mid, "state": state, "source_log": str(path),
                    "molecule": molecule, "spec": spec}
            if not path.exists() and not path.is_symlink():
                case.update(status="missing_log", reason="No source log to inspect")
                cases.append(case)
                continue
            raw = regular_file(path).read_bytes()
            try:
                parsed = parse_log(raw.decode("utf-8", errors="strict"))
            except (ValueError, UnicodeError) as error:
                case.update(status="manual", reason=f"Log cannot be parsed reliably: {error}")
                cases.append(case)
                continue
            result = classify_evidence(parsed)
            case.update(source_log_sha256=hashlib.sha256(raw).hexdigest(),
                        analysis=result, evidence=parsed)
            if result["status"] == "not_no_G298":
                case.update(status=result["status"], reason=result["reason"])
            else:
                job_id = recorded_job_id(method, mid, state)
                life = lifecycle(job_id, args.logs_finished)
                case.update(job_id=job_id, lifecycle=life)
                if life["status"] != "finished":
                    case.update(status=life["status"], reason=life["reason"])
                elif parsed["charge_multiplicity"] != [(spec["charge"], spec["multiplicity"])]:
                    case.update(status="manual", reason="Log charge/multiplicity does not match saved task parameters")
                else:
                    case.update(status=result["status"], reason=result["reason"])
                    if result["status"] == "candidate":
                        try:
                            parameters = parameters or saved_parameters(method)
                            dependencies = {str(path): case["source_log_sha256"]}
                            for suffix in ("com", "slurm"):
                                dependency = method / "work" / mid / f"{state}.{suffix}"
                                dependencies[str(dependency)] = sha256(dependency)
                            source = source_input(method, molecule, spec, parsed, result, parameters)
                            identity = validate_identity(molecule, spec, result["coordinates"]["atoms"])
                            snapshot.update(dependencies)
                            case.update(status="ready", input=source, identity=identity)
                        except ValueError as error:
                            case.update(status="manual", reason=str(error))
            cases.append(case)
    check_source_snapshot(snapshot)
    report = {"mode": "read_only_preview", "method": str(method), "cases": cases,
              "preparation_enabled": True,
              "notice": "No files or jobs were created. Use --prepare to confirm an independent retry."}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Recovery preview; no files are written and no jobs are submitted.")
        for case in cases:
            point = case.get("analysis", {}).get("selected", {})
            step = f"; candidate step {point['step']}" if point else ""
            print(f"{case['molecule_id']} {case['state']}: {case['status']}{step} -- {case['reason']}")
        print(report["notice"])
    if args.prepare:
        for target in prepare_retries(method, cases, options, parameters, snapshot, args.logs_finished):
            print(f"Prepared: {target}")
            print("Review COM files, then submit separately:")
            print(shlex.join(["bash", str(target / "submit" / "submit.sh")]))


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
