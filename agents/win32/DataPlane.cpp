#include "HiveCore.hpp"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <cstdint>
#include <vector>

static std::atomic<bool> g_data_plane_running{false};
static SOCKET g_local_bridge_socket = INVALID_SOCKET;
static SOCKET g_network_socket = INVALID_SOCKET;
static SOCKET g_listen_socket = INVALID_SOCKET;

void bridge_to_net_worker(SOCKET bridge, SOCKET net) {
    char buffer[131072];
    while (g_data_plane_running) {
        int got = recv(bridge, buffer, sizeof(buffer), 0);
        if (got <= 0) break;
        int sent = send(net, buffer, got, 0);
        if (sent <= 0) break;
    }
}

void net_to_bridge_worker(SOCKET net, SOCKET bridge) {
    char buffer[131072];
    while (g_data_plane_running) {
        int got = recv(net, buffer, sizeof(buffer), 0);
        if (got <= 0) break;
        int sent = send(bridge, buffer, got, 0);
        if (sent <= 0) break;
    }
}

void data_plane_worker_internal(SOCKET bridge_sock, std::string peer_ip, int peer_port, bool is_server) {
    SOCKET net_sock = INVALID_SOCKET;
    if (is_server) {
        g_listen_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        int opt = 1; setsockopt(g_listen_socket, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));
        sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_addr.s_addr = INADDR_ANY; addr.sin_port = htons(peer_port);
        if (bind(g_listen_socket, (struct sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
            closesocket(g_listen_socket); g_listen_socket = INVALID_SOCKET;
        } else {
            listen(g_listen_socket, 1);
            net_sock = accept(g_listen_socket, NULL, NULL);
            closesocket(g_listen_socket); g_listen_socket = INVALID_SOCKET;
        }
    } else {
        net_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        sockaddr_in addr{}; addr.sin_family = AF_INET; addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, peer_ip.c_str(), &addr.sin_addr);
        if (connect(net_sock, (struct sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
            net_sock = INVALID_SOCKET;
        }
    }

    if (g_data_plane_running && net_sock != INVALID_SOCKET) {
        g_network_socket = net_sock;
        std::thread t1(bridge_to_net_worker, bridge_sock, net_sock);
        net_to_bridge_worker(net_sock, bridge_sock);
        if (t1.joinable()) t1.join();
    }

    if (net_sock != INVALID_SOCKET) closesocket(net_sock);
    g_network_socket = INVALID_SOCKET;
    closesocket(bridge_sock);
    g_local_bridge_socket = INVALID_SOCKET;
}

json start_data_plane(const json& cmd) {
    if (g_data_plane_running) {
        stop_data_plane();
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    
    std::string peer_ip = cmd.value("peer_ip", "");
    int peer_port = cmd.value("peer_port", 5001);
    bool is_server = peer_ip.empty();

    SOCKET bridge_listen = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in bridge_addr{}; bridge_addr.sin_family = AF_INET; bridge_addr.sin_addr.s_addr = inet_addr("127.0.0.1"); bridge_addr.sin_port = 0;
    bind(bridge_listen, (struct sockaddr*)&bridge_addr, sizeof(bridge_addr));
    listen(bridge_listen, 1);
    int len = sizeof(bridge_addr);
    getsockname(bridge_listen, (struct sockaddr*)&bridge_addr, &len);
    int bridge_port = ntohs(bridge_addr.sin_port);

    g_data_plane_running = true;
    std::thread launcher([=]() {
        SOCKET bridge_conn = accept(bridge_listen, NULL, NULL);
        closesocket(bridge_listen);
        if (bridge_conn != INVALID_SOCKET) {
            g_local_bridge_socket = bridge_conn;
            data_plane_worker_internal(bridge_conn, peer_ip, peer_port, is_server);
        }
    });
    launcher.detach();

    return {{"type", "DATA_PLANE_STARTED"}, {"bridge_port", bridge_port}, {"role", is_server ? "server" : "client"}};
}

json stop_data_plane() {
    g_data_plane_running = false;
    if (g_listen_socket != INVALID_SOCKET) { closesocket(g_listen_socket); g_listen_socket = INVALID_SOCKET; }
    if (g_local_bridge_socket != INVALID_SOCKET) { closesocket(g_local_bridge_socket); g_local_bridge_socket = INVALID_SOCKET; }
    if (g_network_socket != INVALID_SOCKET) { closesocket(g_network_socket); g_network_socket = INVALID_SOCKET; }
    return {{"type", "DATA_PLANE_STOPPED"}};
}
