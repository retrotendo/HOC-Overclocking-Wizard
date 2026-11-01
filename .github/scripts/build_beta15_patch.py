from pathlib import Path


def must_replace(s: str, old: str, new: str, name: str, count: int = 1) -> str:
    if old not in s:
        raise SystemExit(f"beta15 marker missing: {name}")
    return s.replace(old, new, count)


def replace_inside_function(src: str, signature: str, old: str, new: str, name: str) -> str:
    pos = src.find(signature)
    if pos < 0:
        raise SystemExit(f"beta15 function missing: {signature}")
    brace = src.find("{", pos)
    depth = 0
    end = None
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"beta15 unbalanced function: {signature}")
    body = src[pos:end]
    if old not in body:
        raise SystemExit(f"beta15 marker missing in {signature}: {name}")
    body = body.replace(old, new, 1)
    return src[:pos] + body + src[end:]


# Version
p = Path("Makefile")
s = p.read_text()
s = must_replace(s, "APP_VERSION := 0.1.0-beta.14", "APP_VERSION := 0.1.0-beta.15", "version")
p.write_text(s)

# Exact config-value formatter: never round or truncate fractional mV stored in microvolts.
p = Path("source/main_oc.cpp")
s = p.read_text()
old_fmt = '''std::string fmtMvUv(int uv) {
    std::ostringstream o; o << (uv/1000);
    if (uv%1000==500) o << ".5";
    o << " mV"; return o.str();
}'''
new_fmt = '''std::string fmtMvUv(int uv) {
    const bool neg = uv < 0;
    const int a = neg ? -uv : uv;
    const int whole = a / 1000;
    const int rem = a % 1000;
    std::ostringstream o;
    if (neg) o << '-';
    o << whole;
    if (rem) {
        char f[4]; std::snprintf(f,sizeof(f),"%03d",rem);
        std::string frac(f);
        while(!frac.empty() && frac.back()=='0') frac.pop_back();
        o << '.' << frac;
    }
    o << " mV";
    return o.str();
}'''
s = must_replace(s, old_fmt, new_fmt, "exact mV formatter")

# During RAM Max Clock Search, show the benchmark context with the exact tested clock.
s = replace_inside_function(
    s,
    "void runRamCandidate()",
    "auto b=ocbench::runRam();",
    'auto b=ocbench::runRam("RAM "+std::to_string(freq)+" MHz");',
    "RAM benchmark context",
)
p.write_text(s)

# Benchmark API carries an optional display context.
p = Path("source/oc_bench.hpp")
h = p.read_text()
h = must_replace(h, "RamResult runRam();", "RamResult runRam(const std::string& displayContext = {});", "runRam declaration")
p.write_text(h)

# Draw a dedicated RAM benchmark progress page using the existing graphical surface.
p = Path("source/gui_console.hpp")
h = p.read_text()
old_sv = '''struct StressView {
    std::string title;
    std::string subtitle;'''
new_sv = '''struct StressView {
    bool benchmarkMode = false;
    double benchmarkProgress = 0.0;
    std::string title;
    std::string subtitle;'''
h = must_replace(h, old_sv, new_sv, "benchmark view fields")
p.write_text(h)

p = Path("source/oc_bench.cpp")
b = p.read_text()
b = must_replace(b, '#include "hoc_monitor.h"\n', '#include "hoc_monitor.h"\n#include "gui_console.hpp"\n', "benchmark GUI include")
b = must_replace(b, "RamResult runRam() {", "RamResult runRam(const std::string& displayContext) {", "runRam signature")
old_loop = '''    while (bench_step(ctx, &out, &label, &frac)) {
        sample(r.telemetry);
        svcSleepThread(2'000'000);
    }'''
new_loop = '''    while (bench_step(ctx, &out, &label, &frac)) {
        sample(r.telemetry);
        gui::StressView v{};
        v.benchmarkMode = true;
        v.benchmarkProgress = std::clamp(double(frac), 0.0, 1.0);
        v.title = "RAM Memory Benchmark";
        v.subtitle = displayContext.empty() ? "Measuring RAM performance" : displayContext;
        v.detail1 = label ? label : "Memory benchmark";
        v.detail2 = "Measuring bandwidth and latency for the RAM efficiency graph";
        gui::presentStress(v);
        svcSleepThread(2'000'000);
    }
    {
        gui::StressView v{};
        v.benchmarkMode = true;
        v.benchmarkProgress = 1.0;
        v.title = "RAM Memory Benchmark";
        v.subtitle = displayContext.empty() ? "Measuring RAM performance" : displayContext;
        v.detail1 = "Benchmark complete";
        v.detail2 = "Saving bandwidth, latency and performance score";
        gui::presentStress(v);
    }'''
b = must_replace(b, old_loop, new_loop, "RAM benchmark progress loop")
p.write_text(b)

p = Path("source/gui_console.cpp")
g = p.read_text()
needle = '''    drawText(x + 34, y + 104, 16, C_MUTED, fitText(s.subtitle, 16, w - 68));

    const std::uint64_t totalMs = std::uint64_t(std::max(1, s.durationSeconds)) * 1000ULL;'''
replacement = '''    drawText(x + 34, y + 104, 16, C_MUTED, fitText(s.subtitle, 16, w - 68));

    if (s.benchmarkMode) {
        const double progress = std::clamp(s.benchmarkProgress, 0.0, 1.0);
        const int barX = x + 34, barY = y + 176, barW = w - 68;
        roundedRect(barX, barY, barW, 18, 9, C_DARK);
        roundedRect(barX, barY, std::max(18, int(barW * progress)), 18, 9, C_CYAN);
        char pctBuf[16]; std::snprintf(pctBuf,sizeof(pctBuf),"%d%%",int(progress*100.0 + 0.5));
        drawTextRight(x + w - 34, y + 210, 22, C_CYAN, pctBuf);
        drawText(x + 34, y + 250, 17, C_MUTED, "Current benchmark step");
        drawText(x + 34, y + 281, 25, C_TEXT, fitText(s.detail1.empty()?"Memory benchmark":s.detail1,25,w-68));
        drawText(x + 34, y + 342, 17, C_MUTED, fitText(s.detail2,17,w-68));
        roundedRect(x + 34, y + h - 72, w - 68, 46, 11, C_DARK);
        drawText(x + 50, y + h - 61, 17, C_TEXT, "Please wait - the next RAM clock starts automatically");
        endFrame();
        return;
    }

    const std::uint64_t totalMs = std::uint64_t(std::max(1, s.durationSeconds)) * 1000ULL;'''
g = must_replace(g, needle, replacement, "benchmark progress renderer")
p.write_text(g)

# Build-time audit.
main = Path("source/main_oc.cpp").read_text()
bench = Path("source/oc_bench.cpp").read_text()
hpp = Path("source/oc_bench.hpp").read_text()
gui = Path("source/gui_console.cpp").read_text()
guih = Path("source/gui_console.hpp").read_text()
checks = {
    "beta15 version": "0.1.0-beta.15" in Path("Makefile").read_text(),
    "RAM stability still 45s": 'runStress(stress::Kind::Ram,45,"RAM Clock Stability - "' in main,
    "benchmark context clock": 'ocbench::runRam("RAM "+std::to_string(freq)+" MHz")' in main,
    "visible benchmark progress": "benchmarkProgress" in bench and "Current benchmark step" in gui,
    "benchmark labels": "label ? label" in bench,
    "benchmark feeds graph": "r.cpuRead = out.cpu_read" in bench and "r.ramNs = out.ram_ns" in bench and "r.score = oc::ramPerformanceScore" in bench,
    "exact uV formatting": "while(!frac.empty() && frac.back()=='0')" in main,
    "SoC half step retained": "fmtSocConfigMv" in main,
    "config guard retained": "HOC config mismatch before" in main,
    "GPU retained": "GPU + RAM Integration" in main,
    "CPU retained": "CPU + RAM Final Validation" in main,
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
bad = [name for name, ok in checks.items() if not ok]
if bad:
    raise SystemExit("Beta15 source audit failed: " + ", ".join(bad))
