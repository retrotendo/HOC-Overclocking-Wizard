/*
 * Switch memtester interface adapted from Horizon-OC Benchmark Toolbox.
 * Original memtester algorithms are GPL-2.0-only.
 * See source/mt_cpu.c and THIRD_PARTY_LICENSES.md.
 * SPDX-License-Identifier: GPL-2.0-only
 */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint64_t loop;
    const char *test;
    uint64_t mismatches;
    uint64_t burnin_iters;
    int error;
    int done;
    uint64_t total_mb;
    int threads;
    float progress;
} mt_cpu_status_t;

/* mode 0: full CPU memtester; mode 1: memtester + bandwidth burn-in. */
void mt_cpu_start(int mode);
void mt_cpu_stop(void);
int mt_cpu_running(void);
void mt_cpu_get(mt_cpu_status_t *out);

#ifdef __cplusplus
}
#endif
