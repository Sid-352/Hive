#include "json.hpp"
#include "constants.hpp"
#include "dbus_helpers.hpp"
#include <dbus/dbus.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <cstring>
#include <cstdio>
#include <thread>
#include <chrono>
#include <mutex>
#include <condition_variable>
#include <algorithm>

using json = nlohmann::json;

extern void log_message(const char *level, const char *message);

#define LOG_INFO(msg) log_message("INFO", msg)
#define LOG_ERROR(msg) log_message("ERROR", msg)
#define LOG_DEBUG(msg) log_message("DEBUG", msg)
#define LOG_WARNING(msg) log_message("WARNING", msg)

#define NM_SERVICE "org.freedesktop.NetworkManager"
#define NM_PATH "/org/freedesktop/NetworkManager"
#define NM_INTERFACE "org.freedesktop.NetworkManager"
#define NM_DEVICE_INTERFACE "org.freedesktop.NetworkManager.Device"
#define NM_DEVICE_WIFI_INTERFACE "org.freedesktop.NetworkManager.Device.Wireless"
#define NM_SETTINGS_INTERFACE "org.freedesktop.NetworkManager.Settings"
#define NM_CONNECTION_INTERFACE "org.freedesktop.NetworkManager.Settings.Connection"
#define NM_ACTIVE_CONNECTION_INTERFACE "org.freedesktop.NetworkManager.Connection.Active"
#define NM_ACCESS_POINT_INTERFACE "org.freedesktop.NetworkManager.AccessPoint"

static DBusConnection *g_dbus_connection = nullptr;
static std::string g_active_connection_ssid;
static std::string g_active_hotspot_ssid;

void init_dbus_connection() {
  if (g_dbus_connection) return;

  DBusError error;
  dbus_error_init(&error);

  g_dbus_connection = dbus_bus_get(DBUS_BUS_SYSTEM, &error);
  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    throw std::runtime_error("Failed to connect to D-Bus");
  }

  if (!g_dbus_connection) {
    throw std::runtime_error("D-Bus connection is NULL");
  }
}

void cleanup_dbus_connection() {
  if (g_dbus_connection) {
    dbus_connection_unref(g_dbus_connection);
    g_dbus_connection = nullptr;
  }
}

static json get_dbus_property(const char* service, const char* path, const char* interface, const char* property) {
  init_dbus_connection();
  DBusMessage* message = dbus_message_new_method_call(service, path, "org.freedesktop.DBus.Properties", "Get");
  if (!message) return json();

  dbus_message_append_args(message, DBUS_TYPE_STRING, &interface, DBUS_TYPE_STRING, &property, DBUS_TYPE_INVALID);

  DBusError error;
  dbus_error_init(&error);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 2000, &error);
  dbus_message_unref(message);

  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    return json();
  }

  DBusMessageIter iter, variant;
  dbus_message_iter_init(reply, &iter);
  dbus_message_iter_recurse(&iter, &variant);

  json result;
  int type = dbus_message_iter_get_arg_type(&variant);
  
  if (type == DBUS_TYPE_STRING || type == DBUS_TYPE_OBJECT_PATH) {
    char* val;
    dbus_message_iter_get_basic(&variant, &val);
    result = std::string(val);
  } else if (type == DBUS_TYPE_UINT32) {
    dbus_uint32_t val;
    dbus_message_iter_get_basic(&variant, &val);
    result = (uint32_t)val;
  } else if (type == DBUS_TYPE_BOOLEAN) {
    dbus_bool_t val;
    dbus_message_iter_get_basic(&variant, &val);
    result = (bool)val;
  } else if (type == DBUS_TYPE_BYTE) {
    unsigned char val;
    dbus_message_iter_get_basic(&variant, &val);
    result = (int)val;
  } else if (type == DBUS_TYPE_ARRAY) {
    DBusMessageIter array;
    dbus_message_iter_recurse(&variant, &array);
    int subtype = dbus_message_iter_get_arg_type(&array);
    if (subtype == DBUS_TYPE_BYTE) {
        std::string bytes;
        while (dbus_message_iter_get_arg_type(&array) == DBUS_TYPE_BYTE) {
            unsigned char b;
            dbus_message_iter_get_basic(&array, &b);
            bytes += (char)b;
            dbus_message_iter_next(&array);
        }
        result = bytes;
    }
  }

  dbus_message_unref(reply);
  return result;
}

static std::string get_connection_path_by_id(const std::string& connection_id) {
  init_dbus_connection();
  
  DBusMessage* message = dbus_message_new_method_call(NM_SERVICE, "/org/freedesktop/NetworkManager/Settings", NM_SETTINGS_INTERFACE, "ListConnections");
  if (!message) return "";

  DBusError error;
  dbus_error_init(&error);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 3000, &error);
  dbus_message_unref(message);

  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    return "";
  }

  DBusMessageIter iter, array;
  dbus_message_iter_init(reply, &iter);
  
  if (dbus_message_iter_get_arg_type(&iter) == DBUS_TYPE_ARRAY) {
    dbus_message_iter_recurse(&iter, &array);
    while (dbus_message_iter_get_arg_type(&array) == DBUS_TYPE_OBJECT_PATH) {
      char* path;
      dbus_message_iter_get_basic(&array, &path);
      
      json settings = get_dbus_property(NM_SERVICE, path, NM_CONNECTION_INTERFACE, "Id");
      if (settings.is_string() && settings.get<std::string>() == connection_id) {
        std::string result(path);
        dbus_message_unref(reply);
        return result;
      }
      dbus_message_iter_next(&array);
    }
  }

  dbus_message_unref(reply);
  return "";
}

static bool nm_delete_connection(const std::string& connection_id) {
  std::string path = get_connection_path_by_id(connection_id);
  if (path.empty()) return false;

  DBusMessage* message = dbus_message_new_method_call(NM_SERVICE, path.c_str(), NM_CONNECTION_INTERFACE, "Delete");
  if (!message) return false;

  DBusError error;
  dbus_error_init(&error);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 3000, &error);
  dbus_message_unref(message);

  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    return false;
  }

  if (reply) dbus_message_unref(reply);
  return true;
}

static std::vector<std::string> nm_get_connection_ids() {
  init_dbus_connection();
  
  DBusMessage* message = dbus_message_new_method_call(NM_SERVICE, "/org/freedesktop/NetworkManager/Settings", NM_SETTINGS_INTERFACE, "ListConnections");
  if (!message) return {};

  DBusError error;
  dbus_error_init(&error);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 3000, &error);
  dbus_message_unref(message);

  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    return {};
  }

  std::vector<std::string> connection_ids;
  DBusMessageIter iter, array;
  dbus_message_iter_init(reply, &iter);
  
  if (dbus_message_iter_get_arg_type(&iter) == DBUS_TYPE_ARRAY) {
    dbus_message_iter_recurse(&iter, &array);
    while (dbus_message_iter_get_arg_type(&array) == DBUS_TYPE_OBJECT_PATH) {
      char* path;
      dbus_message_iter_get_basic(&array, &path);
      
      json id = get_dbus_property(NM_SERVICE, path, NM_CONNECTION_INTERFACE, "Id");
      if (id.is_string()) {
        connection_ids.push_back(id.get<std::string>());
      }
      dbus_message_iter_next(&array);
    }
  }

  dbus_message_unref(reply);
  return connection_ids;
}

json perform_startup_cleanup() {
  int cleanup_count = 0;
  std::vector<std::string> ids = nm_get_connection_ids();
  for (const auto& id : ids) {
    if (id.find(Hive::SSID_PREFIX) == 0) {
      if (nm_delete_connection(id)) cleanup_count++;
    }
  }
  if (cleanup_count > 0) {
    char log_buf[128];
    snprintf(log_buf, sizeof(log_buf), "WifiManager: Cleaned up %d orphaned connections.", cleanup_count);
    LOG_INFO(log_buf);
    return {{"type", "CLEANUP_SUCCESS"}, {"count", cleanup_count}};
  }
  return {{"type", "CLEANUP_CHECK"}, {"status", "none"}};
}

static bool is_imposter(const char* path) {
    json iface = get_dbus_property(NM_SERVICE, path, NM_DEVICE_INTERFACE, "Interface");
    if (!iface.is_string()) return true;
    std::string name = iface.get<std::string>();
    
    if (name.find("docker") == 0 || name.find("veth") == 0 || name.find("br-") == 0 || 
        name.find("virbr") == 0 || name.find("lo") == 0) {
        return true;
    }
    
    json driver = get_dbus_property(NM_SERVICE, path, NM_DEVICE_INTERFACE, "Driver");
    if (driver.is_string()) {
        std::string drv = driver.get<std::string>();
        if (drv == "veth" || drv == "bridge" || drv == "tun") return true;
    }
    return false;
}

static std::string get_wifi_device_path() {
  DBusMessage* message = dbus_message_new_method_call(NM_SERVICE, NM_PATH, NM_INTERFACE, "GetDevices");
  if (!message) return "";

  DBusError error;
  dbus_error_init(&error);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 3000, &error);
  dbus_message_unref(message);

  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    return "";
  }

  DBusMessageIter iter, array;
  dbus_message_iter_init(reply, &iter);
  if (dbus_message_iter_get_arg_type(&iter) == DBUS_TYPE_ARRAY) {
    dbus_message_iter_recurse(&iter, &array);
    while (dbus_message_iter_get_arg_type(&array) == DBUS_TYPE_OBJECT_PATH) {
      char* path;
      dbus_message_iter_get_basic(&array, &path);
      
      if (is_imposter(path)) {
          dbus_message_iter_next(&array);
          continue;
      }

      json type = get_dbus_property(NM_SERVICE, path, NM_DEVICE_INTERFACE, "DeviceType");
      if (type.is_number() && type.get<uint32_t>() == 2) {
        std::string result(path);
        dbus_message_unref(reply);
        return result;
      }
      dbus_message_iter_next(&array);
    }
  }
  dbus_message_unref(reply);
  return "";
}

std::vector<json> scan_wifi_direct(int duration_sec) {
  std::vector<json> groups;
  init_dbus_connection();

  std::string device_path = get_wifi_device_path();
  if (device_path.empty()) {
    return groups;
  }

  DBusMessage* message = dbus_message_new_method_call(NM_SERVICE, device_path.c_str(), NM_DEVICE_WIFI_INTERFACE, "RequestScan");
  if (message) {
    DBusMessageIter iter, dict;
    dbus_message_iter_init_append(message, &iter);
    dbus_message_iter_open_container(&iter, DBUS_TYPE_ARRAY, "{sv}", &dict);
    dbus_message_iter_close_container(&iter, &dict);
    DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 3000, NULL);
    if (reply) dbus_message_unref(reply);
    dbus_message_unref(message);
  }

  std::this_thread::sleep_for(std::chrono::seconds(duration_sec));

  message = dbus_message_new_method_call(NM_SERVICE, device_path.c_str(), NM_DEVICE_WIFI_INTERFACE, "GetAllAccessPoints");
  DBusError error;
  dbus_error_init(&error);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 3000, &error);
  dbus_message_unref(message);

  if (dbus_error_is_set(&error)) {
    dbus_error_free(&error);
    return groups;
  }

  DBusMessageIter iter, array;
  dbus_message_iter_init(reply, &iter);
  if (dbus_message_iter_get_arg_type(&iter) == DBUS_TYPE_ARRAY) {
    dbus_message_iter_recurse(&iter, &array);
    while (dbus_message_iter_get_arg_type(&array) == DBUS_TYPE_OBJECT_PATH) {
      char* ap_path;
      dbus_message_iter_get_basic(&array, &ap_path);
      
      json ssid_raw = get_dbus_property(NM_SERVICE, ap_path, NM_ACCESS_POINT_INTERFACE, "Ssid");
      if (ssid_raw.is_string()) {
        std::string ssid = ssid_raw.get<std::string>();
        if (ssid.find("DIRECT-") == 0) {
          json strength = get_dbus_property(NM_SERVICE, ap_path, NM_ACCESS_POINT_INTERFACE, "Strength");
          json hwaddr = get_dbus_property(NM_SERVICE, ap_path, NM_ACCESS_POINT_INTERFACE, "HwAddress");
          
          groups.push_back({
            {"name", ssid},
            {"uuid", hwaddr.is_string() ? hwaddr.get<std::string>() : ssid},
            {"rssi", strength.is_number() ? (int)strength.get<uint32_t>() : -100}
          });
        }
      }
      dbus_message_iter_next(&array);
    }
  }
  dbus_message_unref(reply);
  return groups;
}

static std::string add_and_activate_connection(const json& settings, const std::string& device_path) {
    DBusMessage* message = dbus_message_new_method_call(NM_SERVICE, NM_PATH, NM_INTERFACE, "AddAndActivateConnection");
    if (!message) return "";

    DBusMessageIter iter, dict;
    dbus_message_iter_init_append(message, &iter);
    
    dbus_message_iter_open_container(&iter, DBUS_TYPE_ARRAY, "{sa{sv}}", &dict);
    for (auto& [section, props] : settings.items()) {
        DBusMessageIter section_entry, props_dict;
        dbus_message_iter_open_container(&dict, DBUS_TYPE_DICT_ENTRY, NULL, &section_entry);
        const char* section_name = section.c_str();
        dbus_message_iter_append_basic(&section_entry, DBUS_TYPE_STRING, &section_name);
        
        dbus_message_iter_open_container(&section_entry, DBUS_TYPE_ARRAY, "{sv}", &props_dict);
        for (auto& [key, val] : props.items()) {
            if (val.is_string()) {
                std::string s = val.get<std::string>();
                if (key == "ssid" || key == "psk") {
                    append_byte_array_entry(&props_dict, key.c_str(), s.c_str(), s.length());
                } else {
                    const char* v = s.c_str();
                    append_dict_entry(&props_dict, key.c_str(), DBUS_TYPE_STRING, &v);
                }
            } else if (val.is_number_unsigned()) {
                uint32_t v = val.get<uint32_t>();
                append_dict_entry(&props_dict, key.c_str(), DBUS_TYPE_UINT32, &v);
            } else if (val.is_boolean()) {
                dbus_bool_t v = val.get<bool>();
                append_dict_entry(&props_dict, key.c_str(), DBUS_TYPE_BOOLEAN, &v);
            }
        }
        dbus_message_iter_close_container(&section_entry, &props_dict);
        dbus_message_iter_close_container(&dict, &section_entry);
    }
    dbus_message_iter_close_container(&iter, &dict);
    
    const char* dev_path = device_path.c_str();
    const char* ap_path = "/";
    dbus_message_iter_append_basic(&iter, DBUS_TYPE_OBJECT_PATH, &dev_path);
    dbus_message_iter_append_basic(&iter, DBUS_TYPE_OBJECT_PATH, &ap_path);

    DBusError error;
    dbus_error_init(&error);
    DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, message, 10000, &error);
    dbus_message_unref(message);

    if (dbus_error_is_set(&error)) {
        LOG_ERROR(error.message);
        dbus_error_free(&error);
        return "";
    }

    char *path1 = nullptr, *path2 = nullptr;
    dbus_message_get_args(reply, NULL, DBUS_TYPE_OBJECT_PATH, &path1, DBUS_TYPE_OBJECT_PATH, &path2, DBUS_TYPE_INVALID);
    std::string result = (path2 ? path2 : "");
    dbus_message_unref(reply);
    return result;
}

json create_wifi_direct_group(const std::string& device_id, bool ruthless_mode) {
    std::string ssid = std::string(Hive::SSID_PREFIX) + device_id;
    std::string passphrase(Hive::DEFAULT_PASSPHRASE);
    nm_delete_connection(ssid);

    json settings = {
        {"connection", {{"id", ssid}, {"type", "802-11-wireless"}, {"autoconnect", true}}},
        {"802-11-wireless", {{"ssid", ssid}, {"mode", "ap"}}},
        {"802-11-wireless-security", {{"key-mgmt", "wpa-psk"}, {"psk", passphrase}}},
        {"ipv4", {{"method", "shared"}}},
        {"ipv6", {{"method", "ignore"}}}
    };
    
    if (ruthless_mode) {
        settings["802-11-wireless"]["band"] = "bg";
        settings["802-11-wireless"]["channel"] = 1;
    }

    std::string dev_path = get_wifi_device_path();
    std::string active_path = add_and_activate_connection(settings, dev_path);
    
    if (active_path.empty()) throw std::runtime_error("Failed to activate hotspot natively");
    
    g_active_hotspot_ssid = ssid;
    std::this_thread::sleep_for(std::chrono::seconds(2));

    std::string ip = "10.42.0.1";
    json ip_config_path = get_dbus_property(NM_SERVICE, active_path.c_str(), NM_ACTIVE_CONNECTION_INTERFACE, "Ip4Config");
    if (ip_config_path.is_string()) {
        DBusMessage* msg = dbus_message_new_method_call(NM_SERVICE, ip_config_path.get<std::string>().c_str(), "org.freedesktop.DBus.Properties", "Get");
        const char* iface = "org.freedesktop.NetworkManager.IP4Config";
        const char* prop = "AddressData";
        dbus_message_append_args(msg, DBUS_TYPE_STRING, &iface, DBUS_TYPE_STRING, &prop, DBUS_TYPE_INVALID);
        DBusMessage* reply = dbus_connection_send_with_reply_and_block(g_dbus_connection, msg, 2000, NULL);
        if (reply) {
            DBusMessageIter it, variant, array, entry;
            dbus_message_iter_init(reply, &it);
            dbus_message_iter_recurse(&it, &variant);
            dbus_message_iter_recurse(&variant, &array);
            if (dbus_message_iter_get_arg_type(&array) == DBUS_TYPE_DICT_ENTRY) {
                dbus_message_iter_recurse(&array, &entry);
                while (dbus_message_iter_get_arg_type(&entry) == DBUS_TYPE_DICT_ENTRY) {
                    const char* key;
                    dbus_message_iter_get_basic(&entry, &key);
                    if (strcmp(key, "address") == 0) {
                        DBusMessageIter val_variant;
                        dbus_message_iter_next(&entry);
                        dbus_message_iter_recurse(&entry, &val_variant);
                        char* addr;
                        dbus_message_iter_get_basic(&val_variant, &addr);
                        ip = addr;
                        break;
                    }
                    dbus_message_iter_next(&entry);
                }
            }
            dbus_message_unref(reply);
        }
        dbus_message_unref(msg);
    }

    return {{"type", "GROUP_CREATED"}, {"group_name", ssid}, {"passphrase", passphrase}, {"is_group_owner", true}, {"ip_address", ip}, {"method", "dbus_native"}};
}

json stop_wifi_direct_group() {
    if (!g_active_hotspot_ssid.empty()) {
        nm_delete_connection(g_active_hotspot_ssid);
        g_active_hotspot_ssid.clear();
    }
    return {{"type", "GROUP_STOPPED"}, {"status", "stopped"}};
}

json connect_to_group(const std::string &ssid, const std::string &passphrase) {
    nm_delete_connection(ssid);
    json settings = {
        {"connection", {{"id", ssid}, {"type", "802-11-wireless"}}},
        {"802-11-wireless", {{"ssid", ssid}}},
        {"802-11-wireless-security", {{"key-mgmt", "wpa-psk"}, {"psk", passphrase}}},
        {"ipv4", {{"method", "auto"}}}
    };

    std::string dev_path = get_wifi_device_path();
    std::string active_path = add_and_activate_connection(settings, dev_path);
    if (active_path.empty()) throw std::runtime_error("Native D-Bus connection failed");

    g_active_connection_ssid = ssid;
    return {{"type", "CONNECTED"}, {"group_name", ssid}, {"assigned_ip", "polling"}, {"method", "dbus_native"}};
}

json disconnect_from_group() {
    if (!g_active_connection_ssid.empty()) {
        nm_delete_connection(g_active_connection_ssid);
        g_active_connection_ssid.clear();
    }
    return {{"type", "DISCONNECTED"}, {"status", "success"}};
}

bool is_connected_to_p2p() {
    if (g_active_connection_ssid.empty()) return false;
    std::string path = get_connection_path_by_id(g_active_connection_ssid);
    if (path.empty()) return false;
    return true; 
}

bool is_group_owner_active() {
    return !g_active_hotspot_ssid.empty();
}
