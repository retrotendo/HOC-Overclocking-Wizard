# Third-Party Licenses and Credits

HOC Undervolting Wizard v0.4 incorporates and links against open-source software from other projects. The complete Wizard is distributed under **GNU GPL version 2 only (GPL-2.0-only)** because GPLv2 test code is incorporated into the executable. See [`LICENSE`](LICENSE) for the complete GPLv2 text.

This file records the origin of incorporated test code, the changes made for this project, and the notices required by permissively licensed libraries.

---

## 1. CPU stress: Matrixprod + Hanoi verification

### Source used

The CPU test core in:

- `source/cpu_stress.c`
- `source/cpu_stress.h`

is based on the CPU stress implementation distributed in **Horizon-OC / Benchmark Toolbox**:

- `Source/Benchmark-Toolbox/source/cpustress/cpu_stress.c`
- `Source/Benchmark-Toolbox/source/cpustress/cpu_stress.h`
- https://github.com/Horizon-OC/Horizon-OC

Horizon-OC distributes its relevant code under **GNU GPL version 2**. Benchmark Toolbox bundles the Stress-NX workloads; Stress-NX / MembenchNX is credited in the Switch homebrew community to **Lineon**.

### Changes made by HOC Undervolting Wizard

The original Matrixprod and Hanoi algorithms are retained. The Wizard adds a mode that:

1. runs the Matrixprod workload;
2. runs the Hanoi verification pass after each Matrixprod pass;
3. counts a failed Hanoi verification as an automatic CPU mismatch.

This gives the Wizard the familiar Matrixprod CPU load while also providing automatic arithmetic-error detection.

The modified file carries a GPL-2.0-only SPDX identifier and a modification notice.

### License

**GNU General Public License version 2 only.** See `LICENSE`.

---

## 2. RAM test: memtester v4 algorithms

### Original project

**memtester** — a userspace memory subsystem tester.

Credits retained from the upstream project:

- Originally by **Simon Kirby**
- Version 2 by **Charles Cazabon**
- Version 4 rewrite Copyright (C) 2004-2020 **Charles Cazabon**
- Upstream mirror/source: https://github.com/jnavila/memtester

memtester version 4 is licensed under **GNU GPL version 2 only**.

### Switch adaptation used

The Switch-oriented test definitions and runner in:

- `source/mt_tests.c`
- `source/mt_tests.h`
- `source/mt_cpu.c`
- `source/mt_cpu.h`

are based on the memtester adaptation distributed as part of **Horizon-OC / Benchmark Toolbox**:

- `Source/Benchmark-Toolbox/source/memtester/mt_tests.c`
- `Source/Benchmark-Toolbox/source/memtester/mt_tests.h`
- `Source/Benchmark-Toolbox/source/memtester/mt_cpu.c`
- `Source/Benchmark-Toolbox/source/memtester/mt_cpu.h`
- https://github.com/Horizon-OC/Horizon-OC

The following memtester-style algorithms are present in the Wizard RAM test:

- Stuck Address
- Random Value
- Compare XOR
- Compare SUB
- Compare MUL
- Compare DIV
- Compare OR
- Compare AND
- Sequential Increment
- Solid Bits
- Block Sequential
- Checkerboard
- Bit Spread
- Bit Flip
- Walking Ones
- Walking Zeroes

The Switch runner dynamically maps available memory, runs the test sequence on worker threads, and exposes loop/mismatch/progress information to the Wizard UI.

### Changes made by HOC Undervolting Wizard

- moved the Switch port into this project;
- added explicit upstream, copyright and GPL notices;
- connected the runner to the Wizard timer/progress UI;
- an error or mismatch is propagated directly into the Wizard's automatic FAIL handling.

### License

**GNU General Public License version 2 only.** See `LICENSE`.

---

## 3. Horizon-OC / Benchmark Toolbox

Project: **Horizon-OC**

https://github.com/Horizon-OC/Horizon-OC

Horizon-OC's license file states, among other things, that `memtester` is GPLv2 and that its own relevant modifications are distributed under GPLv2. HOC Undervolting Wizard therefore distributes the derived CPU and RAM test code, and the complete combined work, under GPL-2.0-only.

No code from a standalone unlicensed Stress-NX repository is copied into HOC Undervolting Wizard. The CPU source incorporated here is the GPLv2 version made available in Horizon-OC / Benchmark Toolbox.

---

## 4. deko3d

The Wizard's GPU test is project-original code written against the public **deko3d** API. deko3d itself is linked as a library.

Project: https://github.com/devkitPro/deko3d

Copyright (C) 2018-2020 fincs

> This software is provided 'as-is', without any express or implied
> warranty. In no event will the authors be held liable for any
> damages arising from the use of this software.
>
> Permission is granted to anyone to use this software for any
> purpose, including commercial applications, and to alter it and
> redistribute it freely, subject to the following restrictions:
>
> 1. The origin of this software must not be misrepresented; you
>    must not claim that you wrote the original software. If you use
>    this software in a product, an acknowledgment in the product
>    documentation would be appreciated but is not required.
> 2. Altered source versions must be plainly marked as such, and
>    must not be misrepresented as being the original software.
> 3. This notice may not be removed or altered from any source
>    distribution.

The Wizard does not claim authorship of deko3d.

---

## 5. libnx

HOC Undervolting Wizard uses **libnx** from switchbrew/devkitPro.

Project: https://github.com/switchbrew/libnx

Copyright 2017-2018 libnx Authors

> Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.
>
> THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

## 6. libcurl

The startup self-updater links the devkitPro **switch-curl** port of libcurl for HTTPS access to the GitHub Releases API and release assets.

Project: https://github.com/curl/curl

COPYRIGHT AND PERMISSION NOTICE

Copyright (c) 1996 - 2026, Daniel Stenberg, <daniel@haxx.se>, and many contributors, see the THANKS file.

All rights reserved.

Permission to use, copy, modify, and distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF THIRD PARTY RIGHTS. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Except as contained in this notice, the name of a copyright holder shall not be used in advertising or otherwise to promote the sale, use or other dealings in this Software without prior written authorization of the copyright holder.

---

## Distribution note

When distributing an `.nro` built from this branch, the corresponding source code must remain available under GPL-2.0-only. Publishing the NRO from the same public GitHub repository as its complete buildable source is the intended distribution method for this project.

The in-app test screen also identifies the active upstream test engine and displays the GPL/no-warranty notice.

### Horizon OC live-context IPC used by override pre-flight

`source/hoc_monitor.c` uses the public `hoc:clk` `GetCurrentContext` IPC command and the stable context layout documented by Horizon-OC to read CPU/GPU/RAM Temporary Overrides before a test. The implementation is a reduced read-only adaptation of Horizon-OC's GPLv2 client/context definitions. No Horizon OC configuration is written by this code.
