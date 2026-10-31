/*
 * Interface for the GPLv2 Stress-NX/Benchmark Toolbox CPU stress core.
 * See source/cpu_stress.c and THIRD_PARTY_LICENSES.md.
 * SPDX-License-Identifier: GPL-2.0-only
 */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint64_t iters;
    uint64_t mismatches;
    int threads;
    int running;
} cpu_stress_status_t;

/* mode 0: Matrixprod, mode 1: Hanoi verify,
 * mode 2: Matrixprod + Hanoi verify (Wizard adaptation). */
void cpu_stress_start(int mode);
void cpu_stress_stop(void);
int cpu_stress_running(void);
void cpu_stress_get(cpu_stress_status_t *out);

#ifdef __cplusplus
}
#endif
