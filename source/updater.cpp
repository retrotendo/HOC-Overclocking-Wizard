#include "updater.hpp"
#include "gui_console.hpp"

#include <curl/curl.h>
#include <switch.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/stat.h>
#include <vector>

#ifndef HOC_WIZARD_VERSION
#define HOC_WIZARD_VERSION "0.0.0"
#endif

namespace updater {
namespace {

constexpr const char* RELEASES_API =
    "https://api.github.com/repos/retrotendo/HOC-Undervolting-Wizard/releases?per_page=100";
constexpr const char* UPDATE_MANIFEST =
    "https://raw.githubusercontent.com/retrotendo/HOC-Undervolting-Wizard/main/UPDATE.txt";
constexpr const char* NRO_ASSET = "HOC-Undervolting-Wizard.nro";
constexpr const char* SHA_ASSET = "HOC-Undervolting-Wizard.nro.sha256";
constexpr const char* DEFAULT_SELF =
    "sdmc:/switch/HOC-Undervolting-Wizard/HOC-Undervolting-Wizard.nro";
constexpr const char* USER_AGENT = "HOC-Undervolting-Wizard-Updater/1.0";

struct SemVersion {
    int major = 0;
    int minor = 0;
    int patch = 0;
    int beta = 0;
    bool prerelease = false;
    bool valid = false;
};

struct ReleaseInfo {
    std::string tag;
    std::string version;
    std::string nroUrl;
    std::string shaUrl;
    SemVersion sem;
};

enum class CheckStatus {
    NoUpdate,
    UpdateAvailable,
    Error,
};

size_t writeString(void* ptr, size_t size, size_t nmemb, void* userdata) {
    const size_t total = size * nmemb;
    auto* out = static_cast<std::string*>(userdata);
    out->append(static_cast<const char*>(ptr), total);
    return total;
}

size_t writeFile(void* ptr, size_t size, size_t nmemb, void* userdata) {
    const size_t total = size * nmemb;
    FILE* f = static_cast<FILE*>(userdata);
    return std::fwrite(ptr, 1, total, f) == total ? total : 0;
}

void setCommonCurlOptions(CURL* curl, const char* url) {
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, USER_AGENT);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_MAXREDIRS, 8L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 4L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(curl, CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
}

bool httpGetString(const std::string& url, std::string& out, std::string& error,
                   bool githubApi = false) {
    out.clear();
    CURL* curl = curl_easy_init();
    if (!curl) {
        error = "curl_easy_init failed";
        return false;
    }

    char curlError[CURL_ERROR_SIZE]{};
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Cache-Control: no-cache");
    headers = curl_slist_append(headers, "Pragma: no-cache");
    if (githubApi) {
        headers = curl_slist_append(headers, "Accept: application/vnd.github+json");
        headers = curl_slist_append(headers, "X-GitHub-Api-Version: 2022-11-28");
    }
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

    setCommonCurlOptions(curl, url.c_str());
    curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, curlError);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeString);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &out);

    const CURLcode rc = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);

    if (headers) curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (rc != CURLE_OK) {
        error = curlError[0] ? curlError : curl_easy_strerror(rc);
        return false;
    }
    if (httpCode < 200 || httpCode >= 300) {
        error = "HTTP " + std::to_string(httpCode);
        return false;
    }
    return true;
}

bool downloadToFile(const std::string& url, const std::string& path, std::string& error) {
    std::remove(path.c_str());
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f) {
        error = "Cannot create temporary update file";
        return false;
    }

    CURL* curl = curl_easy_init();
    if (!curl) {
        std::fclose(f);
        std::remove(path.c_str());
        error = "curl_easy_init failed";
        return false;
    }

    char curlError[CURL_ERROR_SIZE]{};
    setCommonCurlOptions(curl, url.c_str());
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 120L);
    curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, curlError);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeFile);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, f);

    const CURLcode rc = curl_easy_perform(curl);
    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);

    const bool fileOk = std::fflush(f) == 0 && std::fclose(f) == 0;
    fsdevCommitDevice("sdmc");

    if (rc != CURLE_OK || httpCode < 200 || httpCode >= 300 || !fileOk) {
        std::remove(path.c_str());
        if (rc != CURLE_OK) error = curlError[0] ? curlError : curl_easy_strerror(rc);
        else if (httpCode < 200 || httpCode >= 300) error = "HTTP " + std::to_string(httpCode);
        else error = "Failed to flush downloaded file";
        return false;
    }

    struct stat st{};
    if (stat(path.c_str(), &st) != 0 || st.st_size < 64 * 1024) {
        std::remove(path.c_str());
        error = "Downloaded NRO is unexpectedly small";
        return false;
    }
    return true;
}

bool jsonStringValue(const std::string& src, const std::string& key, std::string& out,
                     size_t start = 0) {
    const std::string needle = "\"" + key + "\"";
    size_t p = src.find(needle, start);
    if (p == std::string::npos) return false;
    p = src.find(':', p + needle.size());
    if (p == std::string::npos) return false;
    ++p;
    while (p < src.size() && std::isspace(static_cast<unsigned char>(src[p]))) ++p;
    if (p >= src.size() || src[p] != '"') return false;
    ++p;

    out.clear();
    bool escaped = false;
    for (; p < src.size(); ++p) {
        const char c = src[p];
        if (escaped) {
            switch (c) {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                default: out.push_back(c); break;
            }
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else if (c == '"') {
            return true;
        } else {
            out.push_back(c);
        }
    }
    return false;
}

bool jsonBoolValue(const std::string& src, const std::string& key, bool& out) {
    const std::string needle = "\"" + key + "\"";
    size_t p = src.find(needle);
    if (p == std::string::npos) return false;
    p = src.find(':', p + needle.size());
    if (p == std::string::npos) return false;
    ++p;
    while (p < src.size() && std::isspace(static_cast<unsigned char>(src[p]))) ++p;
    if (src.compare(p, 4, "true") == 0) { out = true; return true; }
    if (src.compare(p, 5, "false") == 0) { out = false; return true; }
    return false;
}

bool jsonArrayValue(const std::string& src, const std::string& key, std::string& out) {
    const std::string needle = "\"" + key + "\"";
    size_t p = src.find(needle);
    if (p == std::string::npos) return false;
    p = src.find(':', p + needle.size());
    if (p == std::string::npos) return false;
    p = src.find('[', p + 1);
    if (p == std::string::npos) return false;

    const size_t begin = p;
    int depth = 0;
    bool inString = false;
    bool escaped = false;
    for (; p < src.size(); ++p) {
        const char c = src[p];
        if (inString) {
            if (escaped) escaped = false;
            else if (c == '\\') escaped = true;
            else if (c == '"') inString = false;
            continue;
        }
        if (c == '"') inString = true;
        else if (c == '[') ++depth;
        else if (c == ']') {
            --depth;
            if (depth == 0) {
                out = src.substr(begin, p - begin + 1);
                return true;
            }
        }
    }
    return false;
}

std::vector<std::string> topLevelObjects(const std::string& src) {
    std::vector<std::string> out;
    int depth = 0;
    bool inString = false;
    bool escaped = false;
    size_t begin = std::string::npos;

    for (size_t i = 0; i < src.size(); ++i) {
        const char c = src[i];
        if (inString) {
            if (escaped) escaped = false;
            else if (c == '\\') escaped = true;
            else if (c == '"') inString = false;
            continue;
        }
        if (c == '"') {
            inString = true;
        } else if (c == '{') {
            if (depth == 0) begin = i;
            ++depth;
        } else if (c == '}') {
            if (depth > 0) --depth;
            if (depth == 0 && begin != std::string::npos) {
                out.emplace_back(src.substr(begin, i - begin + 1));
                begin = std::string::npos;
            }
        }
    }
    return out;
}

bool parseSemVersion(std::string raw, SemVersion& out) {
    if (!raw.empty() && (raw[0] == 'v' || raw[0] == 'V')) raw.erase(raw.begin());

    int a = 0, b = 0, c = 0, beta = 0, consumed = 0;
    if (std::sscanf(raw.c_str(), "%d.%d.%d-beta.%d%n", &a, &b, &c, &beta, &consumed) == 4 &&
        consumed == static_cast<int>(raw.size())) {
        out = {a, b, c, beta, true, true};
        return true;
    }

    consumed = 0;
    if (std::sscanf(raw.c_str(), "%d.%d.%d%n", &a, &b, &c, &consumed) == 3 &&
        consumed == static_cast<int>(raw.size())) {
        out = {a, b, c, 0, false, true};
        return true;
    }
    return false;
}

int compareVersion(const SemVersion& a, const SemVersion& b) {
    if (a.major != b.major) return a.major < b.major ? -1 : 1;
    if (a.minor != b.minor) return a.minor < b.minor ? -1 : 1;
    if (a.patch != b.patch) return a.patch < b.patch ? -1 : 1;
    if (a.prerelease != b.prerelease) return a.prerelease ? -1 : 1;
    if (a.prerelease && a.beta != b.beta) return a.beta < b.beta ? -1 : 1;
    return 0;
}

bool findAssetUrls(const std::string& releaseObj, std::string& nroUrl, std::string& shaUrl) {
    std::string assetsJson;
    if (!jsonArrayValue(releaseObj, "assets", assetsJson)) return false;

    for (const auto& asset : topLevelObjects(assetsJson)) {
        std::string name;
        std::string url;
        if (!jsonStringValue(asset, "name", name) ||
            !jsonStringValue(asset, "browser_download_url", url)) continue;
        if (name == NRO_ASSET) nroUrl = url;
        else if (name == SHA_ASSET) shaUrl = url;
    }
    return !nroUrl.empty() && !shaUrl.empty();
}

bool manifestValue(const std::string& text, const std::string& key, std::string& out) {
    const std::string prefix = key + "=";
    size_t pos = 0;
    while (pos <= text.size()) {
        const size_t end = text.find('\n', pos);
        std::string line = text.substr(pos, end == std::string::npos ? std::string::npos : end - pos);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.rfind(prefix, 0) == 0) {
            out = line.substr(prefix.size());
            return !out.empty();
        }
        if (end == std::string::npos) break;
        pos = end + 1;
    }
    return false;
}

CheckStatus checkManifestRelease(ReleaseInfo& latest, std::string& error) {
    std::string text;
    const std::string url = std::string(UPDATE_MANIFEST) + "?current=" + HOC_WIZARD_VERSION;
    if (!httpGetString(url, text, error, false)) return CheckStatus::Error;

    std::string version;
    std::string nroUrl;
    std::string shaUrl;
    if (!manifestValue(text, "version", version) ||
        !manifestValue(text, "nro_url", nroUrl) ||
        !manifestValue(text, "sha_url", shaUrl)) {
        error = "Update manifest is incomplete";
        return CheckStatus::Error;
    }

    SemVersion current;
    SemVersion remote;
    if (!parseSemVersion(HOC_WIZARD_VERSION, current)) {
        error = "Current version string is invalid";
        return CheckStatus::Error;
    }
    if (!parseSemVersion(version, remote)) {
        error = "Update manifest version is invalid";
        return CheckStatus::Error;
    }
    if (compareVersion(remote, current) <= 0) return CheckStatus::NoUpdate;

    latest.version = version;
    latest.tag = "v" + version;
    latest.nroUrl = nroUrl;
    latest.shaUrl = shaUrl;
    latest.sem = remote;
    return CheckStatus::UpdateAvailable;
}

CheckStatus checkLatestRelease(ReleaseInfo& latest, std::string& error) {
    std::string json;
    if (!httpGetString(RELEASES_API, json, error, true)) return CheckStatus::Error;

    SemVersion current;
    if (!parseSemVersion(HOC_WIZARD_VERSION, current)) {
        error = "Current version string is invalid";
        return CheckStatus::Error;
    }

    bool found = false;
    for (const auto& releaseObj : topLevelObjects(json)) {
        bool draft = false;
        if (jsonBoolValue(releaseObj, "draft", draft) && draft) continue;

        std::string tag;
        if (!jsonStringValue(releaseObj, "tag_name", tag)) continue;

        SemVersion sem;
        if (!parseSemVersion(tag, sem)) continue;
        if (compareVersion(sem, current) <= 0) continue;

        std::string nroUrl;
        std::string shaUrl;
        if (!findAssetUrls(releaseObj, nroUrl, shaUrl)) continue;

        if (!found || compareVersion(sem, latest.sem) > 0) {
            latest.tag = tag;
            latest.version = (!tag.empty() && (tag[0] == 'v' || tag[0] == 'V')) ? tag.substr(1) : tag;
            latest.nroUrl = nroUrl;
            latest.shaUrl = shaUrl;
            latest.sem = sem;
            found = true;
        }
    }

    return found ? CheckStatus::UpdateAvailable : CheckStatus::NoUpdate;
}

CheckStatus checkLatestReleaseRobust(ReleaseInfo& latest, std::string& error) {
    ReleaseInfo manifestRelease;
    ReleaseInfo apiRelease;
    std::string manifestError;
    std::string apiError;

    const CheckStatus manifestStatus = checkManifestRelease(manifestRelease, manifestError);
    const CheckStatus apiStatus = checkLatestRelease(apiRelease, apiError);

    const bool manifestUpdate = manifestStatus == CheckStatus::UpdateAvailable;
    const bool apiUpdate = apiStatus == CheckStatus::UpdateAvailable;
    if (manifestUpdate || apiUpdate) {
        if (manifestUpdate && apiUpdate)
            latest = compareVersion(manifestRelease.sem, apiRelease.sem) >= 0 ? manifestRelease : apiRelease;
        else
            latest = manifestUpdate ? manifestRelease : apiRelease;
        return CheckStatus::UpdateAvailable;
    }

    // If either source completed successfully and found nothing newer, that is
    // enough to continue without bothering the user about the other source.
    if (manifestStatus == CheckStatus::NoUpdate || apiStatus == CheckStatus::NoUpdate)
        return CheckStatus::NoUpdate;

    error = "Manifest: " + (manifestError.empty() ? std::string("unknown error") : manifestError) +
            "\nGitHub API: " + (apiError.empty() ? std::string("unknown error") : apiError);
    return CheckStatus::Error;
}

std::string normalizeSelfPath(int argc, char** argv) {
    if (argc > 0 && argv && argv[0]) {
        std::string p = argv[0];
        if (p.size() >= 4 && p.substr(p.size() - 4) == ".nro") {
            if (p.rfind("sdmc:/", 0) == 0) return p;
            if (p.rfind("/switch/", 0) == 0) return "sdmc:" + p;
        }
    }
    return DEFAULT_SELF;
}

bool findExpectedSha256(const std::string& text, std::string& out) {
    for (size_t i = 0; i + 64 <= text.size(); ++i) {
        bool good = true;
        for (size_t j = 0; j < 64; ++j) {
            if (!std::isxdigit(static_cast<unsigned char>(text[i + j]))) {
                good = false;
                break;
            }
        }
        if (!good) continue;
        out = text.substr(i, 64);
        std::transform(out.begin(), out.end(), out.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        return true;
    }
    return false;
}

bool sha256File(const std::string& path, std::string& out, std::string& error) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        error = "Cannot reopen downloaded NRO";
        return false;
    }

    Sha256Context ctx;
    sha256ContextCreate(&ctx);
    unsigned char buf[64 * 1024];
    while (true) {
        const size_t n = std::fread(buf, 1, sizeof(buf), f);
        if (n) sha256ContextUpdate(&ctx, buf, n);
        if (n < sizeof(buf)) {
            if (std::ferror(f)) {
                std::fclose(f);
                error = "Failed while hashing downloaded NRO";
                return false;
            }
            break;
        }
    }
    std::fclose(f);

    unsigned char digest[32];
    sha256ContextGetHash(&ctx, digest);
    static constexpr char HEX[] = "0123456789abcdef";
    out.clear();
    out.reserve(64);
    for (unsigned char b : digest) {
        out.push_back(HEX[(b >> 4) & 0xF]);
        out.push_back(HEX[b & 0xF]);
    }
    return true;
}

bool installRelease(const ReleaseInfo& release, const std::string& selfPath, std::string& error) {
    const std::string newPath = selfPath + ".new";
    const std::string bakPath = selfPath + ".bak";

    std::string checksumText;
    if (!httpGetString(release.shaUrl, checksumText, error, false)) {
        error = "Checksum download failed: " + error;
        return false;
    }

    std::string expectedSha;
    if (!findExpectedSha256(checksumText, expectedSha)) {
        error = "Release checksum is invalid";
        return false;
    }

    if (!downloadToFile(release.nroUrl, newPath, error)) {
        error = "NRO download failed: " + error;
        return false;
    }

    std::string actualSha;
    if (!sha256File(newPath, actualSha, error)) {
        std::remove(newPath.c_str());
        return false;
    }
    if (actualSha != expectedSha) {
        std::remove(newPath.c_str());
        error = "SHA256 verification failed";
        return false;
    }

    struct stat current{};
    if (stat(selfPath.c_str(), &current) != 0) {
        std::remove(newPath.c_str());
        error = "Cannot locate the currently running NRO";
        return false;
    }

    std::remove(bakPath.c_str());
    if (std::rename(selfPath.c_str(), bakPath.c_str()) != 0) {
        std::remove(newPath.c_str());
        error = "Could not create backup of current NRO";
        return false;
    }

    if (std::rename(newPath.c_str(), selfPath.c_str()) != 0) {
        std::rename(bakPath.c_str(), selfPath.c_str());
        fsdevCommitDevice("sdmc");
        std::remove(newPath.c_str());
        error = "Could not replace NRO; old version restored";
        return false;
    }

    fsdevCommitDevice("sdmc");
    return true;
}

void drawChecking() {
    if (gui::isInitialized()) {
        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "UPDATE";
        m.title = "Checking for updates";
        m.body = {"Installed version: " HOC_WIZARD_VERSION, "Checking the latest Wizard release..."};
        m.tone = gui::ModalTone::Cyan;
        gui::presentModal(m);
        return;
    }
    consoleClear();
    std::printf("\x1b[1;1H\x1b[36mHOC Undervolting Wizard\x1b[0m\n");
    std::printf("------------------------------------------------------------\n\n");
    std::printf("Checking for updates...\n\n");
    std::printf("Installed: %s\n", HOC_WIZARD_VERSION);
    consoleUpdate(nullptr);
}

void drawUpdatePrompt(const ReleaseInfo& release) {
    if (gui::isInitialized()) {
        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "UPDATE AVAILABLE";
        m.title = "A newer build is available";
        m.body = {"Installed: " + std::string(HOC_WIZARD_VERSION), "Available: " + release.version, "The downloaded NRO is verified with SHA256 before the current file is replaced."};
        m.primaryAction = "Download & install";
        m.secondaryAction = "Not now";
        m.tone = gui::ModalTone::Green;
        gui::presentModal(m);
        return;
    }
    consoleClear();
    std::printf("\x1b[1;1H\x1b[36mHOC Undervolting Wizard - Update\x1b[0m\n");
    std::printf("------------------------------------------------------------\n\n");
    std::printf("\x1b[32mA newer build is available.\x1b[0m\n\n");
    std::printf("Installed : %s\n", HOC_WIZARD_VERSION);
    std::printf("Available : %s\n\n", release.version.c_str());
    std::printf("[A] Download & install\n");
    std::printf("[B] Not now - continue current version\n");
    consoleUpdate(nullptr);
}

void drawInstalling(const ReleaseInfo& release) {
    if (gui::isInitialized()) {
        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "INSTALLING UPDATE";
        m.title = "Downloading " + release.version;
        m.body = {"The existing NRO is kept until the new file has passed SHA256 verification.", "Do not close the application while the update is being installed."};
        m.tone = gui::ModalTone::Cyan;
        gui::presentModal(m);
        return;
    }
    consoleClear();
    std::printf("\x1b[1;1H\x1b[36mHOC Undervolting Wizard - Update\x1b[0m\n");
    std::printf("------------------------------------------------------------\n\n");
    std::printf("Downloading %s...\n", release.version.c_str());
    std::printf("The existing NRO is not replaced until the new file\n");
    std::printf("has passed SHA256 verification.\n");
    consoleUpdate(nullptr);
}

void drawCheckFailed(const std::string& error) {
    if (gui::isInitialized()) {
        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "UPDATE CHECK FAILED";
        m.title = "Could not check for updates";
        m.body = {error, "You can retry or continue with the currently installed version."};
        m.primaryAction = "Retry";
        m.secondaryAction = "Continue current version";
        m.tone = gui::ModalTone::Red;
        gui::presentModal(m);
        return;
    }
    consoleClear();
    std::printf("\x1b[1;1H\x1b[31mUpdate check failed\x1b[0m\n");
    std::printf("------------------------------------------------------------\n\n");
    std::printf("%s\n\n", error.c_str());
    std::printf("[A] Retry\n");
    std::printf("[B] Continue current version\n");
    consoleUpdate(nullptr);
}

void drawInstallFailed(const std::string& error) {
    if (gui::isInitialized()) {
        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "UPDATE FAILED";
        m.title = "The update could not be installed";
        m.body = {error, "The current NRO was preserved."};
        m.primaryAction = "Retry";
        m.secondaryAction = "Continue current version";
        m.tone = gui::ModalTone::Red;
        gui::presentModal(m);
        return;
    }
    consoleClear();
    std::printf("\x1b[1;1H\x1b[31mUpdate failed\x1b[0m\n");
    std::printf("------------------------------------------------------------\n\n");
    std::printf("%s\n\n", error.c_str());
    std::printf("The current NRO was preserved.\n\n");
    std::printf("[A] Retry\n");
    std::printf("[B] Continue current version\n");
    consoleUpdate(nullptr);
}

void drawInstalled(const ReleaseInfo& release) {
    if (gui::isInitialized()) {
        gui::ModalView m{};
        m.version = HOC_WIZARD_VERSION;
        m.eyebrow = "UPDATE INSTALLED";
        m.title = release.version + " is ready";
        m.body = {"The previous NRO was kept as .bak.", "The running copy is still the old version in memory.", "Exit now and launch HOC Undervolting Wizard again."};
        m.primaryAction = "Exit";
        m.secondaryAction = "Exit";
        m.tone = gui::ModalTone::Green;
        gui::presentModal(m);
        return;
    }
    consoleClear();
    std::printf("\x1b[1;1H\x1b[32mUpdate installed\x1b[0m\n");
    std::printf("------------------------------------------------------------\n\n");
    std::printf("Installed new file: %s\n\n", release.version.c_str());
    std::printf("The previous NRO was kept as .bak.\n");
    std::printf("The running copy is still the old version in memory.\n\n");
    std::printf("Exit now and launch HOC Undervolting Wizard again.\n\n");
    std::printf("[A] Exit   [B] Exit\n");
    consoleUpdate(nullptr);
}

} // namespace

bool startupCheckAndPrompt(PadState& pad, int argc, char** argv) {
    drawChecking();

    const Result socketRc = socketInitializeDefault();
    if (R_FAILED(socketRc)) return false;

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        socketExit();
        return false;
    }

    ReleaseInfo latest;
    std::string error;
    while (true) {
        latest = ReleaseInfo{};
        error.clear();
        const CheckStatus status = checkLatestReleaseRobust(latest, error);
        if (status == CheckStatus::UpdateAvailable) break;
        if (status == CheckStatus::NoUpdate) {
            curl_global_cleanup();
            socketExit();
            return false;
        }

        drawCheckFailed(error);
        bool retry = false;
        while (appletMainLoop()) {
            padUpdate(&pad);
            const u64 k = padGetButtonsDown(&pad);
            if (k & HidNpadButton_A) { retry = true; break; }
            if (k & HidNpadButton_B) {
                curl_global_cleanup();
                socketExit();
                return false;
            }
            svcSleepThread(20'000'000);
        }
        if (!retry) {
            curl_global_cleanup();
            socketExit();
            return true;
        }
        drawChecking();
    }

    const std::string selfPath = normalizeSelfPath(argc, argv);
    drawUpdatePrompt(latest);

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 k = padGetButtonsDown(&pad);

        if (k & HidNpadButton_B) {
            curl_global_cleanup();
            socketExit();
            return false;
        }

        if (k & HidNpadButton_A) {
            while (true) {
                drawInstalling(latest);
                error.clear();
                if (installRelease(latest, selfPath, error)) {
                    curl_global_cleanup();
                    socketExit();
                    drawInstalled(latest);
                    while (appletMainLoop()) {
                        padUpdate(&pad);
                        const u64 exitKeys = padGetButtonsDown(&pad);
                        if (exitKeys & (HidNpadButton_A | HidNpadButton_B)) return true;
                        svcSleepThread(20'000'000);
                    }
                    return true;
                }

                drawInstallFailed(error);
                bool retry = false;
                bool continueOld = false;
                while (appletMainLoop()) {
                    padUpdate(&pad);
                    const u64 failKeys = padGetButtonsDown(&pad);
                    if (failKeys & HidNpadButton_A) { retry = true; break; }
                    if (failKeys & HidNpadButton_B) { continueOld = true; break; }
                    svcSleepThread(20'000'000);
                }
                if (continueOld) {
                    curl_global_cleanup();
                    socketExit();
                    return false;
                }
                if (!retry) {
                    curl_global_cleanup();
                    socketExit();
                    return true;
                }
            }
        }

        svcSleepThread(20'000'000);
    }

    curl_global_cleanup();
    socketExit();
    return true;
}

} // namespace updater
