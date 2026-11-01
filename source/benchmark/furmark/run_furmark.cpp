#include <atomic>
#include <switch.h>
#include <thread>

#include "run_furmark.h"
#include "sates.h"
#include <EGL/egl.h>
#include <glad/glad.h>

// beta1 intentionally embeds only the two Benchmark Toolbox scenes used by the
// Wizard: GPU Furmark (0) and CPU Ray Trace (4). This avoids carrying unrelated
// benchmark scenes/resources into the OC Wizard.
extern void frSceneInit();
extern void frRender();
extern void frExit();
extern void CPURTSceneinit();
extern void CPURTRender();
extern void CPURTExit();

AppState state = STATE_MENU;

namespace {
std::thread g_thread;
std::atomic<bool> g_stop{false};
std::atomic<bool> g_running{false};
std::atomic<float> g_fps{0.0f};
std::atomic<int> g_which{-1};

EGLDisplay s_dpy = EGL_NO_DISPLAY;
EGLContext s_ctx = EGL_NO_CONTEXT;
EGLSurface s_surf = EGL_NO_SURFACE;

bool eglUp() {
    s_dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (s_dpy == EGL_NO_DISPLAY) return false;
    if (!eglInitialize(s_dpy, nullptr, nullptr)) return false;
    if (!eglBindAPI(EGL_OPENGL_API)) return false;

    const EGLint cfgAttr[] = {
        EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_DEPTH_SIZE, 24, EGL_STENCIL_SIZE, 8, EGL_NONE
    };
    EGLConfig cfg{};
    EGLint n = 0;
    if (!eglChooseConfig(s_dpy, cfgAttr, &cfg, 1, &n) || n == 0) return false;

    const EGLint ctxAttr[] = {EGL_CONTEXT_MAJOR_VERSION, 4, EGL_CONTEXT_MINOR_VERSION, 3, EGL_NONE};
    s_ctx = eglCreateContext(s_dpy, cfg, EGL_NO_CONTEXT, ctxAttr);
    if (s_ctx == EGL_NO_CONTEXT) return false;
    if (eglMakeCurrent(s_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, s_ctx) != EGL_TRUE) return false;
    return true;
}

void eglDown() {
    if (s_dpy != EGL_NO_DISPLAY) {
        eglMakeCurrent(s_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (s_ctx != EGL_NO_CONTEXT) eglDestroyContext(s_dpy, s_ctx);
        if (s_surf != EGL_NO_SURFACE) eglDestroySurface(s_dpy, s_surf);
        eglTerminate(s_dpy);
    }
    s_ctx = EGL_NO_CONTEXT;
    s_surf = EGL_NO_SURFACE;
    s_dpy = EGL_NO_DISPLAY;
    eglReleaseThread();
}

bool validScene(int which) { return which == 0 || which == 4; }
void sceneInit(int which) { if (which == 0) frSceneInit(); else CPURTSceneinit(); }
void sceneRender(int which) { if (which == 0) frRender(); else CPURTRender(); }
void sceneExit(int which) { if (which == 0) frExit(); else CPURTExit(); }

void worker(int which) {
    g_which.store(which);
    g_fps.store(0.0f);
    if (!validScene(which) || !eglUp()) {
        eglDown();
        g_which.store(-1);
        g_running.store(false);
        return;
    }
    gladLoadGLLoader((GLADloadproc)eglGetProcAddress);

    GLuint fbo = 0, rbColor = 0, rbDepth = 0;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glGenRenderbuffers(1, &rbColor);
    glBindRenderbuffer(GL_RENDERBUFFER, rbColor);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8, 1280, 720);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rbColor);
    glGenRenderbuffers(1, &rbDepth);
    glBindRenderbuffer(GL_RENDERBUFFER, rbDepth);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, 1280, 720);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, rbDepth);
    glViewport(0, 0, 1280, 720);

    sceneInit(which);
    const u64 frameNs = 16666666ULL;
    u64 fpsT0 = armGetSystemTick();
    int fpsFrames = 0;
    while (!g_stop.load()) {
        const u64 t0 = armGetSystemTick();
        glBindFramebuffer(GL_FRAMEBUFFER, fbo);
        glViewport(0, 0, 1280, 720);
        sceneRender(which);

        GLsync fence = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
        glFlush();
        while (!g_stop.load()) {
            const GLenum r = glClientWaitSync(fence, 0, 0);
            if (r != GL_TIMEOUT_EXPIRED) break;
            svcSleepThread(500000ULL);
        }
        glDeleteSync(fence);

        const u64 dt = armTicksToNs(armGetSystemTick() - t0);
        if (dt < frameNs) svcSleepThread(frameNs - dt);
        ++fpsFrames;
        const u64 elapsed = armTicksToNs(armGetSystemTick() - fpsT0);
        if (elapsed >= 500000000ULL) {
            g_fps.store(float(double(fpsFrames) * 1.0e9 / double(elapsed)));
            fpsFrames = 0;
            fpsT0 = armGetSystemTick();
        }
    }

    sceneExit(which);
    glDeleteFramebuffers(1, &fbo);
    glDeleteRenderbuffers(1, &rbColor);
    glDeleteRenderbuffers(1, &rbDepth);
    eglDown();
    g_fps.store(0.0f);
    g_which.store(-1);
    g_running.store(false);
}
} // namespace

extern "C" void run_furmark_start(int which) {
    if (g_running.load() || !validScene(which)) return;
    if (g_thread.joinable()) g_thread.join();
    g_stop.store(false);
    g_running.store(true);
    appletSetAutoSleepDisabled(true);
    g_thread = std::thread(worker, which);
}

extern "C" void run_furmark_stop(void) {
    g_stop.store(true);
    if (g_thread.joinable()) g_thread.join();
    g_running.store(false);
    appletSetAutoSleepDisabled(false);
}

extern "C" int run_furmark_running(void) { return g_running.load() ? 1 : 0; }
extern "C" float run_furmark_fps(void) { return g_fps.load(); }
extern "C" float run_furmark_cpu_fps(void) { return 0.0f; }
