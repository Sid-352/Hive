#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <string>
#include <vector>
#include <thread>
#include <chrono>
#include <mutex>
#include <random>
#include <algorithm>
#include <fstream>
#include <regex>

#include <winrt/Windows.Devices.Enumeration.h>
#include <winrt/Windows.Devices.WiFi.h>
#include <winrt/Windows.Devices.WiFiDirect.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Networking.h>
#include <winrt/Windows.Security.Credentials.h>

#include <winrt/Windows.Networking.NetworkOperators.h>
#include <winrt/Windows.Networking.Connectivity.h>

#include <wlanapi.h>
#pragma comment(lib, "wlanapi.lib")

#include <iphlpapi.h>
#pragma comment(lib, "iphlpapi.lib")

#include "constants.hpp"
#include "json.hpp"

using json = nlohmann::json;
using namespace winrt;
using namespace Windows::Devices::WiFi;
using namespace Windows::Devices::WiFiDirect;
using namespace Windows::Devices::Enumeration;
using namespace Windows::Foundation;
using namespace Windows::Networking;

extern void log_message(const char *level, const char *message);

#define LOG_INFO(msg) log_message("INFO", msg)
#define LOG_ERROR(msg) log_message("ERROR", msg)
#define LOG_DEBUG(msg) log_message("DEBUG", msg)
#define LOG_WARNING(msg) log_message("WARNING", msg)

WiFiDirectDevice g_current_wfd_device = nullptr;
std::string g_connected_group_ssid;
std::string g_assigned_local_ip;
bool g_is_this_device_group_owner = false;

static std::string g_original_wifi_profile_name;
static std::wstring g_original_wifi_profile_xml;
static GUID g_original_wifi_interface_guid;
static bool g_has_original_wifi_to_restore = false;

static SOCKET g_interface_anchor_socket = INVALID_SOCKET;

Windows::Networking::NetworkOperators::NetworkOperatorTetheringManager g_tethering_manager = nullptr;

static bool g_group_creation_success = false;
static std::string g_group_creation_error;
static std::mutex g_group_mutex;
static std::condition_variable g_group_cv;

static WiFiDirectConnectionListener g_connection_listener = nullptr;

static winrt::event_token g_wfd_status_changed_token{};
static winrt::event_token g_wfd_connection_requested_token{};
static bool g_wfd_tokens_registered = false;

static WiFiDirectAdvertisementPublisher g_wfd_publisher{nullptr};

static void save_restore_info() {
  if (!g_has_original_wifi_to_restore) return;
  
  try {
    json restore_data;
    restore_data["profile_name"] = g_original_wifi_profile_name;
    
    int wide_xml_len = (int)g_original_wifi_profile_xml.length();
    int narrow_xml_len = WideCharToMultiByte(CP_UTF8, 0, g_original_wifi_profile_xml.c_str(), wide_xml_len, nullptr, 0, nullptr, nullptr);
    std::string narrow_xml(narrow_xml_len, 0);
    WideCharToMultiByte(CP_UTF8, 0, g_original_wifi_profile_xml.c_str(), wide_xml_len, &narrow_xml[0], narrow_xml_len, nullptr, nullptr);
    
    restore_data["profile_xml"] = narrow_xml;
    
    RPC_CSTR guid_str = nullptr;
    if (UuidToStringA(&g_original_wifi_interface_guid, &guid_str) == RPC_S_OK) {
      restore_data["interface_guid"] = (char*)guid_str;
      RpcStringFreeA(&guid_str);
    }
    
    std::ofstream out_file(Hive::RESTORE_FILE);
    if (out_file.is_open()) {
      out_file << restore_data.dump();
      out_file.close();
    }
  } catch (...) {
    LOG_ERROR("WifiManager: Failed to save restore info");
  }
}

static void clear_restore_info() {
  _unlink(Hive::RESTORE_FILE);
  g_has_original_wifi_to_restore = false;
  g_original_wifi_profile_name.clear();
  g_original_wifi_profile_xml.clear();
}

static void restore_original_wifi() {
  if (!g_has_original_wifi_to_restore || g_original_wifi_profile_xml.empty()) return;

  char log_buf[256];
  HANDLE wlan_handle = nullptr;
  DWORD current_version = 0;
  if (WlanOpenHandle(2, nullptr, &current_version, &wlan_handle) == ERROR_SUCCESS) {
    DWORD reason_code = 0;
    DWORD result = WlanSetProfile(wlan_handle, &g_original_wifi_interface_guid,
        0, g_original_wifi_profile_xml.c_str(), nullptr, TRUE, nullptr, &reason_code);
    
    if (result == ERROR_SUCCESS) {
      sprintf_s(log_buf, "WifiManager: Restored '%s' to original state", g_original_wifi_profile_name.c_str());
      LOG_INFO(log_buf);
    }
    WlanCloseHandle(wlan_handle, nullptr);
  }
  clear_restore_info();
}

static void gag_current_wifi() {
  if (g_has_original_wifi_to_restore) return;

  char log_buf[512];
  HANDLE wlan_handle = nullptr;
  DWORD current_version = 0;
  if (WlanOpenHandle(2, nullptr, &current_version, &wlan_handle) != ERROR_SUCCESS) return;

  PWLAN_INTERFACE_INFO_LIST interface_list = nullptr;
  if (WlanEnumInterfaces(wlan_handle, nullptr, &interface_list) == ERROR_SUCCESS && interface_list->dwNumberOfItems > 0) {
    GUID interface_guid = interface_list->InterfaceInfo[0].InterfaceGuid;
    
    PWLAN_CONNECTION_ATTRIBUTES connection_attributes = nullptr;
    DWORD attributes_size = 0;
    WLAN_OPCODE_VALUE_TYPE opcode_type = wlan_opcode_value_type_invalid;
    DWORD query_result = WlanQueryInterface(
        wlan_handle, &interface_guid,
        wlan_intf_opcode_current_connection, nullptr,
        &attributes_size, (PVOID*)&connection_attributes, &opcode_type);
    
    if (query_result == ERROR_SUCCESS && connection_attributes != nullptr) {
      if (connection_attributes->strProfileName[0] != L'\0') {
        char profile_name_utf8[256] = {0};
        WideCharToMultiByte(CP_UTF8, 0, connection_attributes->strProfileName, -1,
                            profile_name_utf8, sizeof(profile_name_utf8), nullptr, nullptr);
        
        g_original_wifi_profile_name = profile_name_utf8;
        g_original_wifi_interface_guid = interface_guid;
        
        LPWSTR profile_xml_ptr = nullptr;
        DWORD profile_flags = 0;
        DWORD profile_access = 0;
        if (WlanGetProfile(wlan_handle, &interface_guid,
            connection_attributes->strProfileName, nullptr, &profile_xml_ptr, &profile_flags, &profile_access) == ERROR_SUCCESS) {
          
          g_original_wifi_profile_xml = profile_xml_ptr;
          std::wstring modified_xml(profile_xml_ptr);
          
          std::wregex mode_regex(L"<connectionMode>\\s*auto\\s*</connectionMode>");
          modified_xml = std::regex_replace(modified_xml, mode_regex, L"<connectionMode>manual</connectionMode>");
          
          std::wregex switch_regex(L"<autoSwitch>\\s*true\\s*</autoSwitch>");
          modified_xml = std::regex_replace(modified_xml, switch_regex, L"<autoSwitch>false</autoSwitch>");
          
          DWORD reason_code = 0;
          if (WlanSetProfile(wlan_handle, &interface_guid, 0, modified_xml.c_str(), nullptr, TRUE, nullptr, &reason_code) == ERROR_SUCCESS) {
            WlanDisconnect(wlan_handle, &interface_guid, nullptr);
            g_has_original_wifi_to_restore = true;
            save_restore_info();
            LOG_INFO("WifiManager: Radio freed - home WiFi suppressed");
          }
          WlanFreeMemory(profile_xml_ptr);
        }
      }
      WlanFreeMemory(connection_attributes);
    }
    WlanFreeMemory(interface_list);
  }
  WlanCloseHandle(wlan_handle, nullptr);
}

json perform_startup_restoration() {
  std::ifstream in_file(Hive::RESTORE_FILE);
  if (!in_file.is_open()) {
    return {{"type", "RESTORE_CHECK"}, {"status", "none"}};
  }
  
  try {
    json restore_data;
    in_file >> restore_data;
    in_file.close();
    
    std::string profile_name = restore_data.value("profile_name", "");
    std::string profile_xml_narrow = restore_data.value("profile_xml", "");
    std::string guid_str = restore_data.value("interface_guid", "");
    
    if (profile_name.empty() || profile_xml_narrow.empty() || guid_str.empty()) {
      clear_restore_info();
      return {{"type", "RESTORE_FAILED"}, {"message", "Corrupt restore data"}};
    }
    
    GUID interface_guid;
    if (UuidFromStringA((RPC_CSTR)guid_str.c_str(), &interface_guid) != RPC_S_OK) {
      clear_restore_info();
      return {{"type", "RESTORE_FAILED"}, {"message", "Invalid GUID in restore data"}};
    }
    
    int wide_len = MultiByteToWideChar(CP_UTF8, 0, profile_xml_narrow.c_str(), -1, nullptr, 0);
    std::wstring profile_xml(wide_len, 0);
    MultiByteToWideChar(CP_UTF8, 0, profile_xml_narrow.c_str(), -1, &profile_xml[0], wide_len);
    
    HANDLE wlan_handle = nullptr;
    DWORD current_version = 0;
    if (WlanOpenHandle(2, nullptr, &current_version, &wlan_handle) == ERROR_SUCCESS) {
      DWORD reason_code = 0;
      DWORD result = WlanSetProfile(wlan_handle, &interface_guid, 0, profile_xml.c_str(), nullptr, TRUE, nullptr, &reason_code);
      WlanCloseHandle(wlan_handle, nullptr);
      
      if (result == ERROR_SUCCESS) {
        LOG_INFO("WifiManager: Crash recovery successful! Home WiFi restored.");
        clear_restore_info();
        return {{"type", "RESTORE_SUCCESS"}, {"profile", profile_name}};
      }
    }
  } catch (...) {
  }
  
  clear_restore_info();
  return {{"type", "RESTORE_FAILED"}, {"message", "Exception during restoration"}};
}

static bool is_admin_user() {
  BOOL is_admin = FALSE;
  SID_IDENTIFIER_AUTHORITY nt_auth = SECURITY_NT_AUTHORITY;
  PSID admin_group = nullptr;
  if (AllocateAndInitializeSid(&nt_auth, 2, SECURITY_BUILTIN_DOMAIN_RID,
      DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &admin_group)) {
    CheckTokenMembership(nullptr, admin_group, &is_admin);
    FreeSid(admin_group);
  }
  return is_admin != FALSE;
}

std::string to_narrow(const winrt::hstring &wide) {
  int size = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), -1, nullptr, 0, nullptr, nullptr);
  std::string result(size - 1, 0);
  WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), -1, &result[0], size, nullptr, nullptr);
  return result;
}

winrt::hstring to_wide(const std::string &narrow) {
  int size = MultiByteToWideChar(CP_UTF8, 0, narrow.c_str(), -1, nullptr, 0);
  std::wstring result(size - 1, 0);
  MultiByteToWideChar(CP_UTF8, 0, narrow.c_str(), -1, &result[0], size);
  return winrt::hstring(result);
}

json create_tethering_hotspot(const std::string& device_id, const std::string& passphrase);

std::vector<json> scan_wifi_direct(int duration_sec) {
  std::vector<json> groups;

  try {
    init_apartment();
    
    hstring selector = WiFiAdapter::GetDeviceSelector();
    auto adapters = DeviceInformation::FindAllAsync(selector).get();
    
    if (adapters.Size() == 0) {
      return groups;
    }
    
    auto adapter_id = adapters.GetAt(0).Id();
    auto adapter = WiFiAdapter::FromIdAsync(adapter_id).get();
    
    adapter.ScanAsync().get();
    
    int wait_ms = (duration_sec * 1000 > 1000) ? (duration_sec * 1000) : 1000;
    std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));
    
    auto networks = adapter.NetworkReport().AvailableNetworks();
    
    for (const auto& network : networks) {
      std::string ssid = to_narrow(network.Ssid());
      if (ssid.find("DIRECT-") == 0) {
        json group = {
            {"name", ssid},
            {"uuid", ssid},
            {"rssi", network.NetworkRssiInDecibelMilliwatts()}
        };
        groups.push_back(group);
      }
    }
  } catch (...) {
  }
  return groups;
}

void reset_wifi_direct_state() {
  try {
    if (g_wfd_tokens_registered && g_wfd_publisher) {
      try { g_wfd_publisher.StatusChanged(g_wfd_status_changed_token); } catch (...) {}
    }
    if (g_wfd_tokens_registered && g_connection_listener) {
      try { g_connection_listener.ConnectionRequested(g_wfd_connection_requested_token); } catch (...) {}
    }
    
    g_wfd_tokens_registered = false;
    g_wfd_publisher = nullptr;
    g_connection_listener = nullptr;
    g_group_creation_success = false;
    g_group_creation_error.clear();
    
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  } catch (...) {}
}

int detect_current_frequency() {
  HANDLE wlan_handle = nullptr;
  DWORD current_version = 0;
  if (WlanOpenHandle(2, nullptr, &current_version, &wlan_handle) != ERROR_SUCCESS) return 0;
  
  PWLAN_INTERFACE_INFO_LIST interface_list = nullptr;
  DWORD result = WlanEnumInterfaces(wlan_handle, nullptr, &interface_list);
  
  int frequency = 0;
  if (result == ERROR_SUCCESS && interface_list && interface_list->dwNumberOfItems > 0) {
    GUID interface_guid = interface_list->InterfaceInfo[0].InterfaceGuid;
    PWLAN_BSS_LIST bss_list = nullptr;
    if (WlanGetNetworkBssList(wlan_handle, &interface_guid, nullptr, dot11_BSS_type_any, FALSE, nullptr, &bss_list) == ERROR_SUCCESS) {
      if (bss_list && bss_list->dwNumberOfItems > 0) {
        frequency = (int)bss_list->wlanBssEntries[0].ulChCenterFrequency / 1000;
      }
      if (bss_list) WlanFreeMemory(bss_list);
    }
  }
  if (interface_list) WlanFreeMemory(interface_list);
  WlanCloseHandle(wlan_handle, nullptr);
  return frequency;
}

static void power_cycle_radio() {
  HANDLE wlan_handle = nullptr;
  DWORD current_version = 0;
  if (WlanOpenHandle(2, nullptr, &current_version, &wlan_handle) != ERROR_SUCCESS) return;

  PWLAN_INTERFACE_INFO_LIST interface_list = nullptr;
  if (WlanEnumInterfaces(wlan_handle, nullptr, &interface_list) == ERROR_SUCCESS && interface_list->dwNumberOfItems > 0) {
    GUID interface_guid = interface_list->InterfaceInfo[0].InterfaceGuid;
    
    WLAN_PHY_RADIO_STATE radio_state = {0};
    radio_state.dwPhyIndex = 0;
    radio_state.dot11SoftwareRadioState = dot11_radio_state_off;
    
    LOG_INFO("WifiManager: Power cycling radio to force channel reset...");
    WlanSetInterface(wlan_handle, &interface_guid, wlan_intf_opcode_radio_state, sizeof(radio_state), &radio_state, nullptr);
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    radio_state.dot11SoftwareRadioState = dot11_radio_state_on;
    WlanSetInterface(wlan_handle, &interface_guid, wlan_intf_opcode_radio_state, sizeof(radio_state), &radio_state, nullptr);
    std::this_thread::sleep_for(std::chrono::seconds(5));
  }
  if (interface_list) WlanFreeMemory(interface_list);
  WlanCloseHandle(wlan_handle, nullptr);
}

json create_wifi_direct_group(const std::string& device_id, bool ruthless_mode) {
  LOG_INFO("WifiManager: Creating WiFi Direct group");
  try {
    init_apartment();
    reset_wifi_direct_state();
    
    if (ruthless_mode) {
      power_cycle_radio();
      try {
        json tether_res = create_tethering_hotspot(device_id, std::string(Hive::DEFAULT_PASSPHRASE));
        if (tether_res["type"] != "ERROR") return tether_res;
      } catch (...) {
      }
    }
    
    std::string custom_ssid = std::string(Hive::SSID_PREFIX) + device_id;
    g_wfd_publisher = Windows::Devices::WiFiDirect::WiFiDirectAdvertisementPublisher();
    auto advertisement = g_wfd_publisher.Advertisement();
    advertisement.IsAutonomousGroupOwnerEnabled(true);
    
    auto legacy = advertisement.LegacySettings();
    legacy.IsEnabled(true);
    legacy.Ssid(to_wide(custom_ssid));
    
    auto credential = winrt::Windows::Security::Credentials::PasswordCredential();
    credential.Password(to_wide(std::string(Hive::DEFAULT_PASSPHRASE)));
    legacy.Passphrase(credential);
    
    advertisement.ListenStateDiscoverability(Windows::Devices::WiFiDirect::WiFiDirectAdvertisementListenStateDiscoverability::Normal);
    
    g_wfd_status_changed_token = g_wfd_publisher.StatusChanged([](auto&&, auto args) {
      if (args.Status() == WiFiDirectAdvertisementPublisherStatus::Started) {
        std::lock_guard<std::mutex> lock(g_group_mutex);
        g_group_creation_success = true;
        g_group_cv.notify_all();
      } else if (args.Status() == WiFiDirectAdvertisementPublisherStatus::Aborted) {
        std::lock_guard<std::mutex> lock(g_group_mutex);
        g_group_creation_error = "Publisher aborted";
        g_group_cv.notify_all();
      }
    });
    g_wfd_tokens_registered = true;
    
    g_connection_listener = WiFiDirectConnectionListener();
    g_wfd_connection_requested_token = g_connection_listener.ConnectionRequested([](auto&&, auto args) {
      try {
        auto request = args.GetConnectionRequest();
        auto device_id = request.DeviceInformation().Id();
        auto wfd_device = WiFiDirectDevice::FromIdAsync(device_id).get();
        if (wfd_device) {
          auto endpoints = wfd_device.GetConnectionEndpointPairs();
          if (endpoints.Size() > 0) {
            LOG_INFO(("WifiManager: Client connected! IP: " + winrt::to_string(endpoints.GetAt(0).RemoteHostName().DisplayName())).c_str());
          }
        }
      } catch (...) {}
    });
    
    g_wfd_publisher.Start();
    {
      std::unique_lock<std::mutex> lock(g_group_mutex);
      if (!g_group_cv.wait_for(lock, std::chrono::seconds(10), [] { return g_group_creation_success || !g_group_creation_error.empty(); })) {
        throw std::runtime_error("Group creation timeout");
      }
      if (!g_group_creation_success) throw std::runtime_error(g_group_creation_error);
    }
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    int freq = detect_current_frequency();
    
    return {
      {"type", "GROUP_CREATED"}, 
      {"group_name", custom_ssid}, 
      {"passphrase", Hive::DEFAULT_PASSPHRASE}, 
      {"is_group_owner", true}, 
      {"status", "active"},
      {"band", (freq > 4000) ? "5GHz" : "2.4GHz"},
      {"frequency_mhz", freq}
    };
  } catch (const std::exception& e) {
    LOG_ERROR(e.what());
    throw;
  }
}

json stop_wifi_direct_group() {
  if (g_wfd_publisher) {
    g_wfd_publisher.Stop();
    reset_wifi_direct_state();
    return {{"type", "GROUP_STOPPED"}, {"status", "stopped"}};
  }
  return {{"type", "GROUP_STOPPED"}, {"status", "not_running"}};
}

json create_tethering_hotspot(const std::string& device_id, const std::string& passphrase) {
  char log_buf[512];
  try {
    LOG_INFO("WifiManager: Initializing Ruthless Hotspot (2.4 GHz forced)");
    
    gag_current_wifi();
    std::this_thread::sleep_for(std::chrono::seconds(2));

    auto connection_profile = Windows::Networking::Connectivity::NetworkInformation::GetInternetConnectionProfile();
    if (!connection_profile) {
      auto profiles = Windows::Networking::Connectivity::NetworkInformation::GetConnectionProfiles();
      for (auto const& p : profiles) {
        if (p.IsWlanConnectionProfile() || p.IsWwanConnectionProfile()) {
          connection_profile = p;
          break;
        }
      }
    }

    if (!connection_profile) {
      return {{"type", "ERROR"}, {"message", "No suitable connection profile found"}};
    }

    auto tethering_manager = Windows::Networking::NetworkOperators::NetworkOperatorTetheringManager::CreateFromConnectionProfile(connection_profile);
    if (!tethering_manager) throw std::runtime_error("Failed to create Tethering Manager from profile");

    if (tethering_manager.TetheringOperationalState() == Windows::Networking::NetworkOperators::TetheringOperationalState::On) {
      tethering_manager.StopTetheringAsync().get();
      std::this_thread::sleep_for(std::chrono::seconds(1));
    }
    
    auto configuration = tethering_manager.GetCurrentAccessPointConfiguration();
    std::string ssid = std::string(Hive::SSID_PREFIX) + device_id;
    configuration.Ssid(winrt::to_hstring(ssid));
    configuration.Passphrase(winrt::to_hstring(passphrase.empty() ? Hive::DEFAULT_PASSPHRASE : passphrase));
    
    configuration.Band(Windows::Networking::NetworkOperators::TetheringWiFiBand::TwoPointFourGigahertz);
    
    tethering_manager.ConfigureAccessPointAsync(configuration).get();
    
    auto result = tethering_manager.StartTetheringAsync().get();
    if (result.Status() != Windows::Networking::NetworkOperators::TetheringOperationStatus::Success) {
      throw std::runtime_error("StartTethering failed");
    }
    
    g_tethering_manager = tethering_manager;
    std::this_thread::sleep_for(std::chrono::seconds(1));
    int freq = detect_current_frequency();

    return {
      {"type", "HOTSPOT_CREATED"}, 
      {"ssid", ssid}, 
      {"group_name", ssid}, 
      {"passphrase", Hive::DEFAULT_PASSPHRASE}, 
      {"band", "2.4GHz forced"}, 
      {"status", "active"},
      {"method", "tethering_api"},
      {"frequency_mhz", freq}
    };
  } catch (const std::exception& e) {
    LOG_ERROR((std::string("WifiManager: Tethering Error - ") + e.what()).c_str());
    return {{"type", "ERROR"}, {"message", e.what()}};
  }
}

json stop_tethering_hotspot() {
  if (g_tethering_manager) {
    auto stop_result = g_tethering_manager.StopTetheringAsync().get();
    g_tethering_manager = nullptr;
    restore_original_wifi();
    return {{"type", "HOTSPOT_STOPPED"}, {"status", "success"}};
  }
  return {{"type", "ERROR"}, {"message", "No active hotspot"}};
}

static json find_p2p_ip_address() {
  ULONG buffer_size = 15000;
  std::vector<BYTE> buffer(buffer_size);
  PIP_ADAPTER_ADDRESSES adapter_addresses = (PIP_ADAPTER_ADDRESSES)buffer.data();
  if (GetAdaptersAddresses(AF_INET, GAA_FLAG_INCLUDE_GATEWAYS, nullptr, adapter_addresses, &buffer_size) != NO_ERROR) return json();
  
  auto extract_ip = [](PIP_ADAPTER_ADDRESSES p, char* out_ip, unsigned char* out_octets) -> bool {
    if (p->OperStatus != IfOperStatusUp || !p->FirstUnicastAddress) return false;
    for (auto addr = p->FirstUnicastAddress; addr; addr = addr->Next) {
      if (addr->Address.lpSockaddr->sa_family == AF_INET) {
        unsigned char* octets = (unsigned char*)&addr->Address.lpSockaddr->sa_data[2];
        sprintf_s(out_ip, 32, "%u.%u.%u.%u", octets[0], octets[1], octets[2], octets[3]);
        memcpy(out_octets, octets, 4);
        if (strcmp(out_ip, "0.0.0.0") != 0 && strncmp(out_ip, "127.", 4) != 0) return true;
      }
    }
    return false;
  };

  auto is_imposter = [](const char* d, const char* f) -> bool {
    std::string s = std::string(d) + " " + f;
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return (unsigned char)std::tolower(c); });
    return (s.find("vmware") != std::string::npos || s.find("hyper-v") != std::string::npos || 
            s.find("vbox") != std::string::npos || s.find("wsl") != std::string::npos || s.find("vethernet") != std::string::npos);
  };

  auto build_res = [](const char* ip, unsigned char* o, const char* r, const char* n, DWORD idx) -> json {
    char rip[32]; sprintf_s(rip, "%u.%u.%u.1", o[0], o[1], o[2]);
    return {{"local_ip", std::string(ip)}, {"remote_ip", std::string(rip)}, {"adapter_name", std::string(n)}, {"interface_index", idx}};
  };

  for (auto p = adapter_addresses; p; p = p->Next) {
    char fn[256] = {0}, ds[256] = {0};
    WideCharToMultiByte(CP_UTF8, 0, p->FriendlyName, -1, fn, 256, 0, 0);
    WideCharToMultiByte(CP_UTF8, 0, p->Description, -1, ds, 256, 0, 0);
    if (is_imposter(ds, fn)) continue;
    if (strstr(ds, "Wi-Fi Direct") || strstr(fn, "Local Area Connection*")) {
      char ip[32]; unsigned char oct[4];
      if (extract_ip(p, ip, oct)) return build_res(ip, oct, "ExplicitWFD", fn, p->IfIndex);
    }
  }
  for (auto p = adapter_addresses; p; p = p->Next) {
    char fn[256] = {0}, ds[256] = {0};
    WideCharToMultiByte(CP_UTF8, 0, p->FriendlyName, -1, fn, 256, 0, 0);
    WideCharToMultiByte(CP_UTF8, 0, p->Description, -1, ds, 256, 0, 0);
    if (is_imposter(ds, fn)) continue;
    char ip[32]; unsigned char oct[4];
    if (extract_ip(p, ip, oct)) {
      if (strncmp(ip, "192.168.49.", 11) == 0 || strncmp(ip, "192.168.137.", 12) == 0) return build_res(ip, oct, "P2PSubnet", fn, p->IfIndex);
    }
  }
  return json();
}

json connect_to_group(const std::string &uuid) {
  try {
    init_apartment();
    gag_current_wifi();
    
    HANDLE hWlan = nullptr; DWORD ver = 0;
    if (WlanOpenHandle(2, 0, &ver, &hWlan) != ERROR_SUCCESS) throw std::runtime_error("WlanOpenHandle failed");
    PWLAN_INTERFACE_INFO_LIST pList = nullptr;
    WlanEnumInterfaces(hWlan, 0, &pList);
    if (!pList || pList->dwNumberOfItems == 0) throw std::runtime_error("No WiFi interfaces");
    GUID ifGuid = pList->InterfaceInfo[0].InterfaceGuid;

    std::string profile = "<?xml version=\"1.0\"?><WLANProfile xmlns=\"http://www.microsoft.com/networking/WLAN/profile/v1\">"
      "<name>" + uuid + "</name><SSIDConfig><SSID><name>" + uuid + "</name></SSID></SSIDConfig>"
      "<connectionType>ESS</connectionType><connectionMode>auto</connectionMode><MSM><security><authEncryption>"
      "<authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>"
      "<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>" + std::string(Hive::DEFAULT_PASSPHRASE) + "</keyMaterial></sharedKey>"
      "</security></MSM></WLANProfile>";
    
    int wlen = MultiByteToWideChar(CP_UTF8, 0, profile.c_str(), -1, 0, 0);
    std::vector<wchar_t> wProfile(wlen);
    MultiByteToWideChar(CP_UTF8, 0, profile.c_str(), -1, wProfile.data(), wlen);

    DOT11_SSID ssid; ssid.uSSIDLength = (ULONG)min(uuid.length(), (size_t)32); memcpy(ssid.ucSSID, uuid.c_str(), ssid.uSSIDLength);
    WLAN_CONNECTION_PARAMETERS params = { wlan_connection_mode_temporary_profile, wProfile.data(), &ssid, 0, dot11_BSS_type_any, 0 };

    if (WlanConnect(hWlan, &ifGuid, &params, 0) != ERROR_SUCCESS) throw std::runtime_error("WlanConnect failed");
    
    std::string local_ip = "0.0.0.0";
    std::string remote_ip = "0.0.0.0";
    json net_info;
    for (int i = 0; i < Hive::MAX_IP_POLL_ATTEMPTS; i++) {
      std::this_thread::sleep_for(std::chrono::milliseconds(Hive::IP_POLL_INTERVAL_MS));
      net_info = find_p2p_ip_address();
      if (!net_info.empty()) {
        local_ip = net_info.value("local_ip", "0.0.0.0");
        remote_ip = net_info.value("remote_ip", "0.0.0.0");
        if (local_ip != "0.0.0.0") break;
      }
    }

    if (is_admin_user() && local_ip != "0.0.0.0") {
      std::string adapter_name = net_info["adapter_name"].get<std::string>();

      static std::string last_configured_adapter;
      if (last_configured_adapter != adapter_name) {
          char cmd_buf[512];
          sprintf_s(cmd_buf, "cmd.exe /c netsh interface ip set interface \"%s\" metric=1", adapter_name.c_str());
          system(cmd_buf);
          last_configured_adapter = adapter_name;
      }

      DWORD if_index = net_info["interface_index"].get<DWORD>();
      char cmd_buf[512];
      std::string subnet = remote_ip.substr(0, remote_ip.rfind('.')) + ".0";
      sprintf_s(cmd_buf, "cmd.exe /c route add %s mask 255.255.255.0 %s IF %lu", subnet.c_str(), remote_ip.c_str(), if_index);
      system(cmd_buf);

      g_interface_anchor_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
      if (g_interface_anchor_socket != INVALID_SOCKET) {
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(8080);
        inet_pton(AF_INET, remote_ip.c_str(), &addr.sin_addr);

        u_long non_blocking = 1;
        ioctlsocket(g_interface_anchor_socket, FIONBIO, &non_blocking);
        connect(g_interface_anchor_socket, (struct sockaddr*)&addr, sizeof(addr));
      }
    }

    g_connected_group_ssid = uuid;
    WlanFreeMemory(pList); WlanCloseHandle(hWlan, 0);
    return {{"type", "CONNECTED"}, {"group_uuid", uuid}, {"assigned_ip", local_ip}, {"remote_ip", remote_ip}};
  } catch (const std::exception& e) {
    restore_original_wifi();
    return {{"type", "ERROR"}, {"message", e.what()}};
  }
}

json disconnect_from_group() {
  if (g_interface_anchor_socket != INVALID_SOCKET) {
    closesocket(g_interface_anchor_socket);
    g_interface_anchor_socket = INVALID_SOCKET;
  }
  if (!g_connected_group_ssid.empty()) {
    HANDLE hWlan = nullptr; DWORD ver = 0;
    if (WlanOpenHandle(2, 0, &ver, &hWlan) == ERROR_SUCCESS) {
      PWLAN_INTERFACE_INFO_LIST pList = nullptr;
      if (WlanEnumInterfaces(hWlan, 0, &pList) == ERROR_SUCCESS && pList->dwNumberOfItems > 0) {
        WlanDisconnect(hWlan, &pList->InterfaceInfo[0].InterfaceGuid, 0);
        WlanFreeMemory(pList);
      }
      WlanCloseHandle(hWlan, 0);
    }
    g_connected_group_ssid = "";
  }
  restore_original_wifi();
  return {{"type", "DISCONNECTED"}, {"status", "success"}};
}

bool is_connected_to_p2p() {
  return !g_connected_group_ssid.empty();
}

bool is_group_owner_active() {
  return (g_wfd_publisher && g_wfd_publisher.Status() == WiFiDirectAdvertisementPublisherStatus::Started) ||
         (g_tethering_manager && g_tethering_manager.TetheringOperationalState() == Windows::Networking::NetworkOperators::TetheringOperationalState::On);
}
