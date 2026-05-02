#ifndef HIVE_CORE_HPP
#define HIVE_CORE_HPP

#include "json.hpp"
#include "constants.hpp"
#include <iostream>
#include <string>
#include <vector>
#include <atomic>
#include <thread>
#include <sstream>

#ifdef _WIN32
#include <winsock2.h>
#include <windows.h>
#include <io.h>
#define IS_TTY() (_isatty(_fileno(stdin)))
#define LOG_SPRINTF sprintf_s
#else
#include <unistd.h>
#include <cstdio>
#define IS_TTY() (isatty(STDIN_FILENO))
#define LOG_SPRINTF snprintf
#endif

using json = nlohmann::json;

extern bool is_on_ac_power();
extern int get_ram_gb();
extern int get_logical_cores();
extern int get_vitality_score();
extern void log_message(const char *level, const char *message);

extern std::vector<json> scan_wifi_direct(int duration_sec);
extern json disconnect_from_group();
extern json stop_wifi_direct_group();
extern bool is_connected_to_p2p();
extern bool is_group_owner_active();

extern json start_data_plane(const json& cmd);
extern json stop_data_plane();

inline bool read_exact_bytes(std::function<int(char*, int)> read_fn, char* dst, int total) {
    int got_total = 0;
    while (got_total < total) {
        int got = read_fn(dst + got_total, total - got_total);
        if (got <= 0) return false;
        got_total += got;
    }
    return true;
}

inline uint32_t parse_be32(const char* buf) {
    return (static_cast<uint8_t>(buf[0]) << 24) | (static_cast<uint8_t>(buf[1]) << 16) |
           (static_cast<uint8_t>(buf[2]) << 8) | (static_cast<uint8_t>(buf[3]));
}

#define LOG_INFO(msg) log_message("INFO", msg)
#define LOG_ERROR(msg) log_message("ERROR", msg)
#define LOG_DEBUG(msg) log_message("DEBUG", msg)

enum class AgentState { READY, DISCONNECTED, SCANNING, ASSOCIATING, CONNECTED_AS_CLIENT, CONNECTED_AS_GO };

inline const char* agent_state_to_string(AgentState state) {
    switch (state) {
    case AgentState::READY: return "READY";
    case AgentState::DISCONNECTED: return "DISCONNECTED";
    case AgentState::SCANNING: return "SCANNING";
    case AgentState::ASSOCIATING: return "ASSOCIATING";
    case AgentState::CONNECTED_AS_CLIENT: return "CONNECTED_AS_CLIENT";
    case AgentState::CONNECTED_AS_GO: return "CONNECTED_AS_GO";
    default: return "UNKNOWN";
    }
}

extern std::atomic<bool> g_keep_running;
extern std::atomic<AgentState> g_current_agent_state;
extern bool g_interactive_mode;
extern bool g_debug_mode;

inline void send_json_response(const json &response) {
    std::string json_str = response.dump();
    char log_buf[256];
    LOG_SPRINTF(log_buf, 256, "Response: %.200s", json_str.c_str());
    LOG_DEBUG(log_buf);

    std::cout << json_str << std::endl;

    if (g_interactive_mode) {
        std::string type = response.value("type", "");
        if (type == "STATUS") {
            fprintf(stderr, "  [%s] %s\n", response.value("state", "?").c_str(), response.value("message", "").c_str());
        } else if (type == "SCAN_RESULT") {
            auto groups = response.value("groups", json::array());
            fprintf(stderr, "  Scan: %zu device(s) found\n", groups.size());
            for (size_t i = 0; i < groups.size(); i++) {
                auto& g = groups[i];
                fprintf(stderr, "    %zu. %s\n", i+1, g.value("name", g.value("ssid", "?")).c_str());
            }
        } else if (type == "CONNECTED") {
            fprintf(stderr, "  Connected | Local: %s | Gateway: %s\n", response.value("assigned_ip", "?").c_str(), response.value("remote_ip", "?").c_str());
        } else if (type == "ERROR") {
            fprintf(stderr, "  Error: %s\n", response.value("message", "unknown").c_str());
        } else if (type == "DATA_PLANE_STARTED") {
            fprintf(stderr, "  Data Plane: %s | Role: %s\n", 
                response.value("pipe_path", response.value("socket_path", "?")).c_str(), 
                response.value("role", "client").c_str());
        } else if (type == "TELEMETRY") {
            fprintf(stderr, "  Cores: %d | RAM: %dGB | AC: %s | Vitality: %d\n",
                    response.value("logical_cores", 0),
                    response.value("ram_gb", 0),
                    response.value("on_ac_power", false) ? "yes" : "no",
                    response.value("vitality_score", 0));
        }
    }
}

inline void send_status(const char *state, const char *message) {
    json response = {{"type", "STATUS"}, {"state", state}, {"message", message}};
    if (std::string(state) == "READY") response["version"] = Hive::AGENT_VERSION;
    send_json_response(response);
}

inline void send_error(const char *msg, const char *code = "INTERNAL", const char *ctx = "") {
    json response = {{"type", "ERROR"}, {"error_code", code}, {"message", msg}, {"context", ctx}};
    send_json_response(response);
    LOG_ERROR(msg);
}

inline void send_telemetry_data() {
    try {
        json response = {
            {"type", "TELEMETRY"},
            {"on_ac_power", is_on_ac_power()},
            {"ram_gb", get_ram_gb()},
            {"logical_cores", get_logical_cores()},
            {"vitality_score", get_vitality_score()}
        };
        send_json_response(response);
    } catch (const std::exception &e) { send_error(e.what()); }
}

inline void monitor_connectivity_loop() {
    while (g_keep_running) {
        std::this_thread::sleep_for(std::chrono::seconds(2));
        AgentState current = g_current_agent_state.load();
        if (current == AgentState::SCANNING || current == AgentState::ASSOCIATING || current == AgentState::READY) continue;
        
        bool is_client = is_connected_to_p2p();
        bool is_go = is_group_owner_active();
        
        if (is_go) {
            if (current != AgentState::CONNECTED_AS_GO) {
                LOG_INFO("State transition: CONNECTED_AS_GO (detected)");
                g_current_agent_state = AgentState::CONNECTED_AS_GO;
            }
        } else if (is_client) {
            if (current != AgentState::CONNECTED_AS_CLIENT) {
                LOG_INFO("State transition: CONNECTED_AS_CLIENT (detected)");
                g_current_agent_state = AgentState::CONNECTED_AS_CLIENT;
            }
        } else {
            if (current != AgentState::DISCONNECTED) {
                LOG_INFO("State transition: DISCONNECTED (detected)");
                g_current_agent_state = AgentState::DISCONNECTED;
            }
        }
    }
}

#endif
