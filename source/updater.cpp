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
    "https://api.github.com/repos/retrotendo/HOC-Overclocking-Wizard/releases?per_page=100";
constexpr const char* UPDATE_MANIFEST =
    "https://raw.githubusercontent.com/retrotendo/HOC-Overclocking-Wizard/main/UPDATE.txt";
constexpr const char* NRO_ASSET = "HOC-Overclocking-Wizard.nro";
constexpr const char* SHA_ASSET = "HOC-Overclocking-Wizard.nro.sha256";
constexpr const char* DEFAULT_SELF =
    "sdmc:/switch/HOC-Overclocking-Wizard/HOC-Overclocking-Wizard.nro";
constexpr const char* USER_AGENT = "HOC-Overclocking-Wizard-Updater/1.0";

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
    p = src.find(':', p + nedle.size());
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
    size_t begin = std::string::n²È="25¸‰ôì(€€€€€€€´¹ÁÉ¥µ…ÉåÑ¥½¸€ô€‰½İ¹±½…€˜¥¹ÍÑ…±°ˆì(€€€€€€€´¹Í•½¹‘…ÉåÑ¥½¸€ô€‰9½Ğ¹½Üˆì(€€€€€€€´¹Ñ½¹”€ôÕ¤èé5½‘…±Q½¹”èéÉ••¸ì(€€€€€€€Õ¤èéÁÉ•Í•¹Ñ5½‘…°¡´¤ì(€€€€€€€É•ÑÕÉ¸ì(€€€ô(€€€½¹Í½±•±•…È ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰qàÅ‰lÄìÅ!qàÅ‰lÌÙµ!==Ù•É±½­¥¹œ]¥é…É€´UÁ‘…Ñ•qàÅ‰lÁµq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´µq¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰qàÅ‰lÌÉµ¹•İ•È‰Õ¥±¥Ì…Ù…¥±…‰±”¹qàÅ‰lÁµq¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰%¹ÍÑ…±±•€è€•Íq¸ˆ°!=}]%iI}YIM%=8¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰Ù…¥±…‰±”€è€•Íq¹q¸ˆ°É•±•…Í”¹Ù•ÉÍ¥½¸¹}ÍÑÈ ¤¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰mt½İ¹±½…€˜¥¹ÍÑ…±±q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰m	t9½Ğ¹½Ü€´½¹Ñ¥¹Õ”ÕÉÉ•¹ĞÙ•ÉÍ¥½¹q¸ˆ¤ì(€€€½¹Í½±•UÁ‘…Ñ”¡¹Õ±±ÁÑÈ¤ì)ô()Ù½¥‘É…İ%¹ÍÑ…±±¥¹œ¡½¹ÍĞI•±•…Í•%¹™¼˜É•±•…Í”¤ì(€€€¥˜€¡Õ¤èé¥Í%¹¥Ñ¥…±¥é• ¤¤ì(€€€€€€€Õ¤èé5½‘…±Y¥•Üµíôì(€€€€€€€´¹Ù•ÉÍ¥½¸€ô!=}]%iI}YIM%=8ì(€€€€€€€´¹•å•‰É½Ü€ô€‰%9MQ11%9UAQˆì(€€€€€€€´¹Ñ¥Ñ±”€ô€‰½İ¹±½…‘¥¹œ€ˆ€¬É•±•…Í”¹Ù•ÉÍ¥½¸ì(€€€€€€€´¹‰½‘ä€ôì‰Q¡”•á¥ÍÑ¥¹œ9I<¥Ì­•ÁĞÕ¹Ñ¥°Ñ¡”¹•Ü™¥±”¡…ÌÁ…ÍÍ•M!ÈÔØÙ•É¥™¥…Ñ¥½¸¸ˆ°€‰¼¹½Ğ±½Í”Ñ¡”…ÁÁ±¥…Ñ¥½¸İ¡¥±”Ñ¡”ÕÁ‘…Ñ”¥Ì‰•¥¹œ¥¹ÍÑ…±±•¸‰ôì(€€€€€€€´¹Ñ½¹”€ôÕ¤èé5½‘…±Q½¹”èéå…¸ì(€€€€€€€Õ¤èéÁÉ•Í•¹Ñ5½‘…°¡´¤ì(€€€€€€€É•ÑÕÉ¸ì(€€€ô(€€€½¹Í½±•±•…È ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰qàÅ‰lÄìÅ!qàÅ‰lÌÙµ!==Ù•É±½­¥¹œ]¥é…É€´UÁ‘…Ñ•qàÅ‰lÁµq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´µq¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰½İ¹±½…‘¥¹œ€•Ì¸¸¹q¸ˆ°É•±•…Í”¹Ù•ÉÍ¥½¸¹}ÍÑÈ ¤¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰Q¡”•á¥ÍÑ¥¹œ9I<¥Ì¹½ĞÉ•Á±…•Õ¹Ñ¥°Ñ¡”¹•Ü™¥±•q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰¡…ÌÁ…ÍÍ•M!ÈÔØÙ•É¥™¥…Ñ¥½¸¹q¸ˆ¤ì(€€€½¹Í½±•UÁ‘…Ñ”¡¹Õ±±ÁÑÈ¤ì)ô()Ù½¥‘É…İ¡•­…¥±•¡½¹ÍĞÍÑèéÍÑÉ¥¹œ˜•ÉÉ½È¤ì(€€€¥˜€¡Õ¤èé¥Í%¹¥Ñ¥…±¥é• ¤¤ì(€€€€€€€Õ¤èé5½‘…±Y¥•Üµíôì(€€€€€€€´¹Ù•ÉÍ¥½¸€ô!=}]%iI}YIM%=8ì(€€€€€€€´¹•å•‰É½Ü€ô€‰UAQ!,%1ˆì(€€€€€€€´¹Ñ¥Ñ±”€ô€‰½Õ±¹½Ğ¡•¬™½ÈÕÁ‘…Ñ•Ìˆì(€€€€€€€´¹‰½‘ä€ôí•ÉÉ½È°€‰e½Ô…¸É•ÑÉä½È½¹Ñ¥¹Õ”İ¥Ñ Ñ¡”ÕÉÉ•¹Ñ±ä¥¹ÍÑ…±±•Ù•ÉÍ¥½¸¸‰ôì(€€€€€€€´¹ÁÉ¥µ…ÉåÑ¥½¸€ô€‰I•ÑÉäˆì(€€€€€€€´¹Í•½¹‘…ÉåÑ¥½¸€ô€‰½¹Ñ¥¹Õ”ÕÉÉ•¹ĞÙ•ÉÍ¥½¸ˆì(€€€€€€€´¹Ñ½¹”€ôÕ¤èé5½‘…±Q½¹”èéI•ì(€€€€€€€Õ¤èéÁÉ•Í•¹Ñ5½‘…°¡´¤ì(€€€€€€€É•ÑÕÉ¸ì(€€€ô(€€€½¹Í½±•±•…È ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰qàÅ‰lÄìÅ!qàÅ‰lÌÅµUÁ‘…Ñ”¡•¬™…¥±•‘qàÅ‰lÁµq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´µq¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ•Íq¹q¸ˆ°•ÉÉ½È¹}ÍÑÈ ¤¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰mtI•ÑÉåq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰m	t½¹Ñ¥¹Õ”ÕÉÉ•¹ĞÙ•ÉÍ¥½¹q¸ˆ¤ì(€€€½¹Í½±•UÁ‘…Ñ”¡¹Õ±±ÁÑÈ¤ì)ô()Ù½¥‘É…İ%¹ÍÑ…±±…¥±•¡½¹ÍĞÍÑèéÍÑÉ¥¹œ˜•ÉÉ½È¤ì(€€€¥˜€¡Õ¤èé¥Í%¹¥Ñ¥…±¥é• ¤¤ì(€€€€€€€Õ¤èé5½‘…±Y¥•Üµíôì(€€€€€€€´¹Ù•ÉÍ¥½¸€ô!=}]%iI}YIM%=8ì(€€€€€€€´¹•å•‰É½Ü€ô€‰UAQ%1ˆì(€€€€€€€´¹Ñ¥Ñ±”€ô€‰Q¡”ÕÁ‘…Ñ”½Õ±¹½Ğ‰”¥¹ÍÑ…±±•ˆì(€€€€€€€´¹‰½‘ä€ôí•ÉÉ½È°€‰Q¡”ÕÉÉ•¹Ğ9I<İ…ÌÁÉ•Í•ÉÙ•¸‰ôì(€€€€€€€´¹ÁÉ¥µ…ÉåÑ¥½¸€ô€‰I•ÑÉäˆì(€€€€€€€´¹Í•½¹‘…ÉåÑ¥½¸€ô€‰½¹Ñ¥¹Õ”ÕÉÉ•¹ĞÙ•ÉÍ¥½¸ˆì(€€€€€€€´¹Ñ½¹”€ôÕ¤èé5½‘…±Q½¹”èéI•ì(€€€€€€€Õ¤èéÁÉ•Í•¹Ñ5½‘…°¡´¤ì(€€€€€€€É•ÑÕÉ¸ì(€€€ô(€€€½¹Í½±•±•…È ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰qàÅ‰lÄìÅ!qàÅ‰lÌÅµUÁ‘…Ñ”™…¥±•‘qàÅ‰lÁµq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´µq¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ•Íq¹q¸ˆ°•ÉÉ½È¹}ÍÑÈ ¤¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰Q¡”ÕÉÉ•¹Ğ9I<İ…ÌÁÉ•Í•ÉÙ•¹q¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰mtI•ÑÉåq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰m	t½¹Ñ¥¹Õ”ÕÉÉ•¹ĞÙ•ÉÍ¥½¹q¸ˆ¤ì(€€€½¹Í½±•UÁ‘…Ñ”¡¹Õ±±ÁÑÈ¤ì)ô()Ù½¥‘É…İ%¹ÍÑ…±±•¡½¹ÍĞI•±•…Í•%¹™¼˜É•±•…Í”¤ì(€€€¥˜€¡Õ¤èé¥Í%¹¥Ñ¥…±¥é• ¤¤ì(€€€€€€€Õ¤èé5½‘…±Y¥•Üµíôì(€€€€€€€´¹Ù•ÉÍ¥½¸€ô!=}]%iI}YIM%=8ì(€€€€€€€´¹•å•‰É½Ü€ô€‰UAQ%9MQ11ˆì(€€€€€€€´¹Ñ¥Ñ±”€ôÉ•±•…Í”¹Ù•ÉÍ¥½¸€¬€ˆ¥ÌÉ•…‘äˆì(€€€€€€€´¹‰½‘ä€ôì‰Q¡”ÁÉ•Ù¥½ÕÌ9I<İ…Ì­•ÁĞ…Ì€¹‰…¬¸ˆ°€‰Q¡”ÉÕ¹¹¥¹œ½Áä¥ÌÍÑ¥±°Ñ¡”½±Ù•ÉÍ¥½¸¥¸µ•µ½Éä¸ˆ°€‰á¥Ğ¹½Ü…¹±…Õ¹ !==Ù•É±½­¥¹œ]¥é…É……¥¸¸‰ôì(€€€€€€€´¹ÁÉ¥µ…ÉåÑ¥½¸€ô€‰á¥Ğˆì(€€€€€€€´¹Í•½¹‘…ÉåÑ¥½¸€ô€‰á¥Ğˆì(€€€€€€€´¹Ñ½¹”€ôÕ¤èé5½‘…±Q½¹”èéÉ••¸ì(€€€€€€€Õ¤èéÁÉ•Í•¹Ñ5½‘…°¡´¤ì(€€€€€€€É•ÑÕÉ¸ì(€€€ô(€€€½¹Í½±•±•…È ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰qàÅ‰lÄìÅ!qàÅ‰lÌÉµUÁ‘…Ñ”¥¹ÍÑ…±±•‘qàÅ‰lÁµq¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ˆ´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´´µq¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰%¹ÍÑ…±±•¹•Ü™¥±”è€•Íq¹q¸ˆ°É•±•…Í”¹Ù•ÉÍ¥½¸¹}ÍÑÈ ¤¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰Q¡”ÁÉ•Ù¥½ÕÌ9I<İ…Ì­•ÁĞ…Ì€¹‰…¬¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰Q¡”ÉÕ¹¹¥¹œ½Áä¥ÌÍÑ¥±°Ñ¡”½±Ù•ÉÍ¥½¸¥¸µ•µ½Éä¹q¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰á¥Ğ¹½Ü…¹±…Õ¹ !==Ù•É±½­¥¹œ]¥é…É……¥¸¹q¹q¸ˆ¤ì(€€€ÍÑèéÁÉ¥¹Ñ˜ ‰mtá¥Ğ€€m	tá¥Ñq¸ˆ¤ì(€€€½¹Í½±•UÁ‘…Ñ”¡¹Õ±±ÁÑÈ¤ì)ô()ô€¼¼¹…µ•ÍÁ…”()‰½½°ÍÑ…ÉÑÕÁ¡•­¹‘AÉ½µÁĞ¡A…‘MÑ…Ñ”˜Á…°¥¹Ğ…ÉŒ°¡…È¨¨…ÉØ¤ì(€€€‘É…İ¡•­¥¹œ ¤ì((€€€€¼¼9•Ñİ½É¬Í½­•ÑÌ…É”½İ¹•‰äµ…¥¸ ¤¸I”µ¥¹¥Ñ¥…±¥é¥¹œ±¥‰¹àÍ½­•ÑÌ¡•É”(€€€€¼¼…¸™…¥°¥µµ•‘¥…Ñ•±ä…¹Í¥±•¹Ñ±äÍ­¥ÀÑ¡”•¹Ñ¥É”ÍÑ…ÉÑÕÀÕÁ‘…Ñ”¡•¬¸(€€€¥˜€¡ÕÉ±}±½‰…±}¥¹¥Ğ¡UI1}1=	1}U1P¤€„ôUI1}=,¤ì(€€€€€€€É•ÑÕÉ¸™…±Í”ì(€€€ô((€€€I•±•…Í•%¹™¼±…Ñ•ÍĞì(€€€ÍÑèéÍÑÉ¥¹œ•ÉÉ½Èì(€€€İ¡¥±”€¡ÑÉÕ”¤ì(€€€€€€€±…Ñ•ÍĞ€ôI•±•…Í•%¹™½íôì(€€€€€€€•ÉÉ½È¹±•…È ¤ì(€€€€€€€½¹ÍĞ¡•­MÑ…ÑÕÌÍÑ…ÑÕÌ€ô¡•­1…Ñ•ÍÑI•±•…Í•I½‰ÕÍĞ¡±…Ñ•ÍĞ°•ÉÉ½È¤ì(€€€€€€€¥˜€¡ÍÑ…ÑÕÌ€ôô¡•­MÑ…ÑÕÌèéUÁ‘…Ñ•Ù…¥±…‰±”¤‰É•…¬ì(€€€€€€€¥˜€¡ÍÑ…ÑÕÌ€ôô¡•­MÑ…ÑÕÌèé9½UÁ‘…Ñ”¤ì(€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€É•ÑÕÉ¸™…±Í”ì(€€€€€€€ô((€€€€€€€‘É…İ¡•­…¥±•¡•ÉÉ½È¤ì(€€€€€€€‰½½°É•ÑÉä€ô™…±Í”ì(€€€€€€€İ¡¥±”€¡…ÁÁ±•Ñ5…¥¹1½½À ¤¤ì(€€€€€€€€€€€Á…‘UÁ‘…Ñ” ™Á…¤ì(€€€€€€€€€€€½¹ÍĞÔØĞ¬€ôÁ…‘•Ñ	ÕÑÑ½¹Í½İ¸ ™Á…¤ì(€€€€€€€€€€€¥˜€¡¬€˜!¥‘9Á…‘	ÕÑÑ½¹}¤ìÉ•ÑÉä€ôÑÉÕ”ì‰É•…¬ìô(€€€€€€€€€€€¥˜€¡¬€˜!¥‘9Á…‘	ÕÑÑ½¹}¤ì(€€€€€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€€€€€É•ÑÕÉ¸™…±Í”ì(€€€€€€€€€€€ô(€€€€€€€€€€€ÍÙM±••ÁQ¡É•… ÈÀœÀÀÀœÀÀÀ¤ì(€€€€€€€ô(€€€€€€€¥˜€ …É•ÑÉä¤ì(€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€É•ÑÕÉ¸ÑÉÕ”ì(€€€€€€€ô(€€€€€€€‘É…İ¡•­¥¹œ ¤ì(€€€ô((€€€½¹ÍĞÍÑèéÍÑÉ¥¹œÍ•±™A…Ñ €ô¹½Éµ…±¥é•M•±™A…Ñ ¡…ÉŒ°…ÉØ¤ì(€€€‘É…İUÁ‘…Ñ•AÉ½µÁĞ¡±…Ñ•ÍĞ¤ì((€€€İ¡¥±”€¡…ÁÁ±•Ñ5…¥¹1½½À ¤¤ì(€€€€€€€Á…‘UÁ‘…Ñ” ™Á…¤ì(€€€€€€€½¹ÍĞÔØĞ¬€ôÁ…‘•Ñ	ÕÑÑ½¹Í½İ¸ ™Á…¤ì((€€€€€€€¥˜€¡¬€˜!¥‘9Á…‘	ÕÑÑ½¹}¤ì(€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€É•ÑÕÉ¸™…±Í”ì(€€€€€€€ô((€€€€€€€¥˜€¡¬€˜!¥‘9Á…‘	ÕÑÑ½¹}¤ì(€€€€€€€€€€€İ¡¥±”€¡ÑÉÕ”¤ì(€€€€€€€€€€€€€€€‘É…İ%¹ÍÑ…±±¥¹œ¡±…Ñ•ÍĞ¤ì(€€€€€€€€€€€€€€€•ÉÉ½È¹±•…È ¤ì(€€€€€€€€€€€€€€€¥˜€¡¥¹ÍÑ…±±I•±•…Í”¡±…Ñ•ÍĞ°Í•±™A…Ñ °•ÉÉ½È¤¤ì(€€€€€€€€€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€€€€€€€€€‘É…İ%¹ÍÑ…±±•¡±…Ñ•ÍĞ¤ì(€€€€€€€€€€€€€€€€€€€İ¡¥±”€¡…ÁÁ±•Ñ5…¥¹1½½À ¤¤ì(€€€€€€€€€€€€€€€€€€€€€€€Á…‘UÁ‘…Ñ” ™Á…¤ì(€€€€€€€€€€€€€€€€€€€€€€€½¹ÍĞÔØĞ•á¥Ñ-•åÌ€ôÁ…‘•Ñ	ÕÑÑ½¹Í½İ¸ ™Á…¤ì(€€€€€€€€€€€€€€€€€€€€€€€¥˜€¡•á¥Ñ-•åÌ€˜€¡!¥‘9Á…‘	ÕÑÑ½¹}ğ!¥‘9Á…‘	ÕÑÑ½¹}¤¤É•ÑÕÉ¸ÑÉÕ”ì(€€€€€€€€€€€€€€€€€€€€€€€ÍÙM±••ÁQ¡É•… ÈÀœÀÀÀœÀÀÀ¤ì(€€€€€€€€€€€€€€€€€€€ô(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸ÑÉÕ”ì(€€€€€€€€€€€€€€€ô((€€€€€€€€€€€€€€€‘É…İ%¹ÍÑ…±±…¥±•¡•ÉÉ½È¤ì(€€€€€€€€€€€€€€€‰½½°É•ÑÉä€ô™…±Í”ì(€€€€€€€€€€€€€€€‰½½°½¹Ñ¥¹Õ•=±€ô™…±Í”ì(€€€€€€€€€€€€€€€İ¡¥±”€¡…ÁÁ±•Ñ5…¥¹1½½À ¤¤ì(€€€€€€€€€€€€€€€€€€€Á…‘UÁ‘…Ñ” ™Á…¤ì(€€€€€€€€€€€€€€€€€€€½¹ÍĞÔØĞ™…¥±-•åÌ€ôÁ…‘•Ñ	ÕÑÑ½¹Í½İ¸ ™Á…¤ì(€€€€€€€€€€€€€€€€€€€¥˜€¡™…¥±-•åÌ€˜!¥‘9Á…‘	ÕÑÑ½¹}¤ìÉ•ÑÉä€ôÑÉÕ”ì‰É•…¬ìô(€€€€€€€€€€€€€€€€€€€¥˜€¡™…¥±-•åÌ€˜!¥‘9Á…‘	ÕÑÑ½¹}¤ì½¹Ñ¥¹Õ•=±€ôÑÉÕ”ì‰É•…¬ìô(€€€€€€€€€€€€€€€€€€€ÍÙM±••ÁQ¡É•… ÈÀœÀÀÀœÀÀÀ¤ì(€€€€€€€€€€€€€€€ô(€€€€€€€€€€€€€€€¥˜€¡½¹Ñ¥¹Õ•=±¤ì(€€€€€€€€€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸™…±Í”ì(€€€€€€€€€€€€€€€ô(€€€€€€€€€€€€€€€¥˜€ …É•ÑÉä¤ì(€€€€€€€€€€€€€€€€€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€€€€€€€€€€€€€€€€€É•ÑÕÉ¸ÑÉÕ”ì(€€€€€€€€€€€€€€€ô(€€€€€€€€€€€ô(€€€€€€€ô((€€€€€€€ÍÙM±••ÁQ¡É•… ÈÀœÀÀÀœÀÀÀ¤ì(€€€ô((€€€ÕÉ±}±½‰…±}±•…¹ÕÀ ¤ì(€€€É•ÑÕÉ¸ÑÉÕ”ì)ô()ô€¼¼¹…µ•ÍÁ…”ÕÁ‘…Ñ•È(