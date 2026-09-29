#!/usr/bin/env python3
"""Mutation check: apply each single-line mutation to a scratch copy of firmware/ and require the firmware tests to FAIL.
Usage: python3 tools_mutate.py   (exit 1 if any mutant survives). Mutants are (file, old, new) exact-substring replacements."""
import os, shutil, subprocess, sys, tempfile

MUTANTS = [
    ("core/oi_sched.c", "late >= s->counts_per_dot", "late > s->counts_per_dot"),
    ("core/oi_sched.c", "(size_t)s->next_col * s->bytes_per_col", "(size_t)s->next_col"),
    ("core/oi_sched.c", "target - (int64_t)pos", "(int64_t)pos - target"),
    ("core/oi_sched.c", "if (dir == 0 ||", "if ("),
    ("core/oi_sched.c", "s->counts_per_dot <= 0", "s->counts_per_dot < 0"),
    ("core/oi_proto.c", "p->len > OI_MAX_PAYLOAD", "p->len > OI_MAX_PAYLOAD + 1"),
    ("core/oi_proto.c", "p->crc_errors++; return OI_BAD;\n    }", "return OI_BAD;\n    }"),
    ("core/oi_job.c", "(uint64_t)cols * bpc > j->cap", "(uint64_t)cols * bpc >= j->cap"),
    ("core/oi_job.c", "(uint64_t)cols * bpc > j->cap", "(uint32_t)cols * bpc > j->cap"),
    ("core/oi_job.c", "if (!j->have_hdr || p->len < 4) return 0;", "if (p->len < 4) return 0;"),
    ("core/oi_job.c", "if (p->len != 13) return 0;", "if (p->len < 13) return 0;"),
    ("core/oi_job.c", "j->received = 0; j->have_hdr = 1;", "j->have_hdr = 1;"),
    ("core/oi_job.c", "j->started = 0;", "j->started = j->started;"),
    ("core/oi_job.c", "if (ok == 0) j->naks++;", ""),
    ("core/oi_job.c", "j->started = 1; j->pass_ready = 1;", "j->pass_ready = 1;"),
    ("core/oi_job.c", "if (r) { j->pass_ready = 0; j->busy = 1; }", "if (r) { j->pass_ready = 0; }"),
    ("core/oi_job.c", "void oi_job_pass_done(oi_job_t *j) { j->busy = 0; }", "void oi_job_pass_done(oi_job_t *j) { (void)j; }"),
    ("core/oi_job.c", "if ((size_t)off + n <= j->received)", "if ((size_t)off + n < j->received)"),
    ("core/oi_head_matrix.c", "p >= n_prim", "p > n_prim"),
    ("core/oi_head_matrix.c", "n_addr > OI_MATRIX_MAX_ADDR", "n_addr > OI_MATRIX_MAX_ADDR + 1"),
    ("core/oi_head_matrix.c", "n_prim > 32", "n_prim > 33"),
    ("core/oi_head_matrix.c", "    memset(seen, 0, sizeof seen);\n", ""),
    ("core/oi_motion.c", "(uint64_t)v_max * v_max", "(uint32_t)v_max * v_max"),
    ("core/oi_motion.c", "cand * cand <= v2", "cand * cand < v2"),
    ("core/oi_motion.c", "return v > 0xFFFFFFFFull ? 0xFFFFFFFFu : (uint32_t)v;", "return (uint32_t)v;"),
    ("core/oi_motion.c", "return steps_per_mm_x1000 ? 0 : -1;", "return 0;"),
    ("core/oi_motion.c", "return num / 1000000ull;", "return (uint32_t)(num / 1000000ull);"),
    ("core/oi_maint.c", "if (m->idle_ms >= m->idle_cap_after_ms)", "if (m->idle_ms > m->idle_cap_after_ms)"),
    ("core/oi_maint.c", "m->idle_ms = 0;\n    if (m->state == M_CAPPED)", "if (m->state == M_CAPPED)"),
    ("core/oi_maint.c", "m->pages_since_wipe = 0; m->state = M_WIPING;", "m->state = M_WIPING;"),
    ("core/oi_maint.c", "return A_BUSY;", "return A_NONE;"),
    ("core/oi_maint.c", "if (m->state == M_FAULT) { m->state = M_CAPPED;", "if (m->state == M_FAULT) { m->state = M_READY;"),
]
CF = "-std=c99 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror -fsanitize=address,undefined".split()
BUILDS = [
    ("test_sched", ["tests/test_sched.c", "core/oi_sched.c"], []),
    ("test_proto", ["tests/test_proto.c", "core/oi_proto.c"], ["VECTORS"]),
    ("test_modules", ["tests/test_modules.c", "core/oi_head_matrix.c", "core/oi_motion.c", "core/oi_maint.c", "core/oi_job.c", "core/oi_proto.c"], []),
    ("fuzz_job", ["tests/fuzz_job.c", "core/oi_job.c", "core/oi_proto.c"], ["200000"]),
]


def run_tests(d, vectors):
    for name, srcs, args in BUILDS:
        exe = os.path.join(d, name)
        b = subprocess.run(["gcc"] + CF + ["-o", exe] + srcs, cwd=d, capture_output=True)
        if b.returncode:
            return "build"
        a = [vectors if x == "VECTORS" else x for x in args]
        if subprocess.run([exe] + a, cwd=d, capture_output=True, timeout=300).returncode:
            return "killed"
    return "survived"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "firmware")
    vectors = sys.argv[1] if len(sys.argv) > 1 else None
    if not vectors or not os.path.exists(vectors):
        sys.exit("usage: tools_mutate.py <vectors.bin produced by run_tests.sh>")
    survived, invalid = [], []
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "fw")
        for i, (f, old, new) in enumerate(MUTANTS):
            shutil.rmtree(d, ignore_errors=True); shutil.copytree(src, d)
            path = os.path.join(d, f); text = open(path).read()
            if old not in text:
                invalid.append((i, f, old)); continue
            open(path, "w").write(text.replace(old, new, 1))
            r = run_tests(d, vectors)
            print("%2d %-8s %s: %s -> %s" % (i, r, f, old[:45].replace("\n", " "), new[:35].replace("\n", " ")))
            if r == "survived":
                survived.append((i, f, old))
            elif r == "build":
                invalid.append((i, f, "does not compile"))
    print("mutants: %d, killed: %d, survived: %d, invalid: %d" % (len(MUTANTS), len(MUTANTS) - len(survived) - len(invalid), len(survived), len(invalid)))
    for s in survived: print("SURVIVED", s)
    for s in invalid: print("INVALID ", s)
    sys.exit(1 if survived or invalid else 0)


main()
