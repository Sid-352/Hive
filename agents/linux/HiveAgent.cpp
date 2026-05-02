#include "HiveCore.hpp"
#include <iostream>
#include <csignal>

const char *g_agent_version = Hive::AGENT_VERSION;

extern json connect_to_group(const std::string &ssid, const std::string &passphrase = "Hive12345678");
extern json create_wifi_direct_group(const std::string& device_id, bool ruthless_mode);
extern json stop_wifi_direct_group();
extern json perform_startup_cleanup();

bool g_debug_mode = false;
bool g_interactive_mode = false;
std::atomic<bool> g_keep_running{true};
std::atomic<AgentState> g_current_agent_state{AgentState::READY};

void cleanup_on_exit() {
    g_keep_running = false;
    try { disconnect_from_group(); } catch (...) {}
    try { stop_wifi_direct_group(); } catch (...) {}
}

void signal_handler(int signal_code) {
    (void)signal_code;
    LOG_INFO("Received termination signal, cleaning up...");
    cleanup_on_exit();
    exit(0);
}

static json parse_shorthand(const std::string& input) {
    std::vector<std::string> tokens;
    std::istringstream iss(input);
    std::string t;
    while (iss >> t) tokens.push_back(t);
    if (tokens.empty()) return json();
    std::string cmd = tokens[0];
    for (auto& c : cmd) c = (char)toupper(c);
    json j; j["type"] = cmd;
    if (cmd == "SCAN" && tokens.size() > 1) j["duration"] = std::stoi(tokens[1]);
    else if (cmd == "CREATE_GROUP") {
        if (tokens.size() > 1) j["device_id"] = tokens[1];
        for (size_t i = 2; i < tokens.size(); i++) {
            if (tokens[i] == "--ruthless" || tokens[i] == "-r") j["ruthless_mode"] = true;
        }
    } else if (cmd == "CONNECT") {
        if (tokens.size() > 1) j["uuid"] = tokens[1];
        if (tokens.size() > 2) j["passphrase"] = tokens[2];
    } else if (cmd == "START_DATA_PLANE") {
        if (tokens.size() > 1) j["peer_ip"] = tokens[1];
        if (tokens.size() > 2) j["peer_port"] = std::stoi(tokens[2]);
    } else if (cmd == "HELP") {
        fprintf(stderr,
            "Commands:\n"
            "  STATUS                         Show agent state\n"
            "  SCAN [duration]                Scan for WiFi Direct groups\n"
            "  CREATE_GROUP <id> [--ruthless]  Create WiFi Direct group\n"
            "  STOP_GROUP                     Stop group\n"
            "  CONNECT <ssid> [pass]          Connect to group\n"
            "  DISCONNECT                     Disconnect from group\n"
            "  START_DATA_PLANE [ip] [port]   Start hybrid data plane\n"
            "  STOP_DATA_PLANE                Stop data streaming server\n"
            "  GET_TELEMETRY                  Show system info\n"
            "  QUIT                           Exit agent\n"
        );
        return json();
    } else if (cmd == "QUIT" || cmd == "EXIT") { cleanup_on_exit(); exit(0); }
    if (cmd == "TELEMETRY") j["type"] = "GET_TELEMETRY";
    return j;
}

void handle_command(const json &cmd) {
    try {
        std::string type = cmd.value("type", "");
        if (type == "STATUS") send_status(agent_state_to_string(g_current_agent_state.load()), "Agent operational");
        else if (type == "GET_TELEMETRY") send_telemetry_data();
        else if (type == "SCAN") {
            g_current_agent_state = AgentState::SCANNING;
            auto res = scan_wifi_direct(cmd.value("duration", 5));
            g_current_agent_state = AgentState::DISCONNECTED;
            send_json_response({{"type", "SCAN_RESULT"}, {"groups", res}});
        } else if (type == "CONNECT") {
            g_current_agent_state = AgentState::ASSOCIATING;
            json res = connect_to_group(cmd.value("uuid", cmd.value("ssid", "")), cmd.value("passphrase", "Hive12345678"));
            if (res["type"] == "CONNECTED") g_current_agent_state = AgentState::CONNECTED_AS_CLIENT;
            else g_current_agent_state = AgentState::DISCONNECTED;
            send_json_response(res);
        } else if (type == "DISCONNECT") {
            send_json_response(disconnect_from_group());
            g_current_agent_state = AgentState::DISCONNECTED;
        } else if (type == "CREATE_GROUP") {
            json res = create_wifi_direct_group(cmd.value("device_id", "LINUX"), cmd.value("ruthless_mode", false));
            if (res["type"] == "GROUP_CREATED") g_current_agent_state = AgentState::CONNECTED_AS_GO;
            send_json_response(res);
        } else if (type == "STOP_GROUP") {
            send_json_response(stop_wifi_direct_group());
            g_current_agent_state = AgentState::DISCONNECTED;
        } else if (type == "START_DATA_PLANE") send_json_response(start_data_plane(cmd));
        else if (type == "STOP_DATA_PLANE") send_json_response(stop_data_plane());
        else if (type == "SHUTDOWN") exit(0);
        else send_error("Unknown command", "UNKNOWN_COMMAND");
    } catch (const std::exception &e) { send_error(e.what()); }
}

int main(int argc, char *argv[]) {
    for (int i = 1; i < argc; i++) if (std::string(argv[i]) == "--debug") g_debug_mode = true;
    std::cout.setf(std::ios::unitbuf);
    g_interactive_mode = IS_TTY();
    if (g_interactive_mode) fprintf(stderr, "Hive Agent (Linux) v%s\n", g_agent_version);
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    std::thread monitor_thread(monitor_connectivity_loop);
    monitor_thread.detach();
    perform_startup_cleanup();
    send_status("READY", "Hardware agent initialized");
    std::string line;
    if (g_interactive_mode) fprintf(stderr, "hive> ");
    while (std::getline(std::cin, line)) {
        if (line.empty()) { if (g_interactive_mode) fprintf(stderr, "hive> "); continue; }
        try {
            if (line[0] == '{') handle_command(json::parse(line));
            else if (g_interactive_mode) {
                json j = parse_shorthand(line);
                if (!j.empty()) handle_command(j);
            }
        } catch (...) { send_error("Invalid input"); }
        if (g_interactive_mode) fprintf(stderr, "hive> ");
    }
    cleanup_on_exit();
    return 0;
}
