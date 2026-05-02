#include "HiveCore.hpp"
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <thread>
#include <vector>
#include <atomic>

static std::atomic<bool> g_data_plane_running{false};
static int g_pipe_fd = -1;
static int g_network_fd = -1;
static int g_listen_net_fd = -1;

void relay_worker(int from_fd, int to_fd, const char* name) {
    char buffer[131072];
    while (g_data_plane_running) {
        ssize_t got = read(from_fd, buffer, sizeof(buffer));
        if (got <= 0) break;
        ssize_t sent = write(to_fd, buffer, got);
        if (sent <= 0) break;
    }
}

void data_plane_worker(std::string peer_ip, int peer_port, bool is_server) {
    std::string sock_path = Hive::DATA_SOCKET_LINUX_BASE + std::to_string(peer_port) + ".sock";
    
    while (g_data_plane_running) {
        int pipe_sock = socket(AF_UNIX, SOCK_STREAM, 0);
        struct sockaddr_un addr_un;
        memset(&addr_un, 0, sizeof(addr_un));
        addr_un.sun_family = AF_UNIX;
        strncpy(addr_un.sun_path, sock_path.c_str(), sizeof(addr_un.sun_path) - 1);
        unlink(sock_path.c_str());
        
        if (bind(pipe_sock, (struct sockaddr*)&addr_un, sizeof(addr_un)) == -1) {
            close(pipe_sock);
            std::this_thread::sleep_for(std::chrono::seconds(1));
            continue;
        }
        
        listen(pipe_sock, 1);
        g_pipe_fd = pipe_sock;
        
        int client_pipe = accept(pipe_sock, NULL, NULL);
        if (client_pipe == -1) {
            close(pipe_sock);
            continue;
        }

        int net_sock = -1;
        if (is_server) {
            g_listen_net_fd = socket(AF_INET, SOCK_STREAM, 0);
            int opt = 1;
            setsockopt(g_listen_net_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
            struct sockaddr_in addr_in;
            memset(&addr_in, 0, sizeof(addr_in));
            addr_in.sin_family = AF_INET;
            addr_in.sin_addr.s_addr = INADDR_ANY;
            addr_in.sin_port = htons(peer_port);
            
            if (bind(g_listen_net_fd, (struct sockaddr*)&addr_in, sizeof(addr_in)) == -1) {
                close(g_listen_net_fd);
                g_listen_net_fd = -1;
            } else {
                listen(g_listen_net_fd, 1);
                net_sock = accept(g_listen_net_fd, NULL, NULL);
                close(g_listen_net_fd);
                g_listen_net_fd = -1;
            }
        } else {
            net_sock = socket(AF_INET, SOCK_STREAM, 0);
            struct sockaddr_in addr_in;
            memset(&addr_in, 0, sizeof(addr_in));
            addr_in.sin_family = AF_INET;
            addr_in.sin_port = htons(peer_port);
            inet_pton(AF_INET, peer_ip.c_str(), &addr_in.sin_addr);
            
            if (connect(net_sock, (struct sockaddr*)&addr_in, sizeof(addr_in)) == -1) {
                close(net_sock);
                net_sock = -1;
            }
        }

        if (g_data_plane_running && net_sock != -1) {
            g_network_fd = net_sock;
            std::thread t1(relay_worker, client_pipe, net_sock, "Pipe->Net");
            relay_worker(net_sock, client_pipe, "Net->Pipe");
            if (t1.joinable()) t1.join();
        }

        if (net_sock != -1) close(net_sock);
        close(client_pipe);
        close(pipe_sock);
        g_network_fd = -1;
        g_pipe_fd = -1;
        unlink(sock_path.c_str());
        
        if (!is_server) break;
    }
}

json start_data_plane(const json& cmd) {
    if (g_data_plane_running) {
        stop_data_plane();
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    
    std::string peer_ip = cmd.value("peer_ip", "");
    int peer_port = cmd.value("peer_port", 5001);
    bool is_server = peer_ip.empty();
    
    g_data_plane_running = true;
    std::thread worker(data_plane_worker, peer_ip, peer_port, is_server);
    worker.detach();
    
    std::string sock_path = Hive::DATA_SOCKET_LINUX_BASE + std::to_string(peer_port) + ".sock";
    return {{"type", "DATA_PLANE_STARTED"}, {"socket_path", sock_path}, {"role", is_server ? "server" : "client"}};
}

json stop_data_plane() {
    g_data_plane_running = false;
    if (g_listen_net_fd != -1) { shutdown(g_listen_net_fd, SHUT_RDWR); close(g_listen_net_fd); g_listen_net_fd = -1; }
    if (g_pipe_fd != -1) { shutdown(g_pipe_fd, SHUT_RDWR); close(g_pipe_fd); g_pipe_fd = -1; }
    if (g_network_fd != -1) { shutdown(g_network_fd, SHUT_RDWR); close(g_network_fd); g_network_fd = -1; }
    return {{"type", "DATA_PLANE_STOPPED"}};
}
