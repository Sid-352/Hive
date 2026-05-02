#include <dbus/dbus.h>

static void append_dict_entry(DBusMessageIter* iter, const char* key, int type, const void* value) {
    DBusMessageIter entry, variant;
    dbus_message_iter_open_container(iter, DBUS_TYPE_DICT_ENTRY, NULL, &entry);
    dbus_message_iter_append_basic(&entry, DBUS_TYPE_STRING, &key);
    
    char type_str[2] = {(char)type, 0};
    dbus_message_iter_open_container(&entry, DBUS_TYPE_VARIANT, type_str, &variant);
    dbus_message_iter_append_basic(&variant, type, value);
    dbus_message_iter_close_container(&entry, &variant);
    
    dbus_message_iter_close_container(iter, &entry);
}

static void append_byte_array_entry(DBusMessageIter* iter, const char* key, const void* data, int len) {
    DBusMessageIter entry, variant, array;
    dbus_message_iter_open_container(iter, DBUS_TYPE_DICT_ENTRY, NULL, &entry);
    dbus_message_iter_append_basic(&entry, DBUS_TYPE_STRING, &key);
    
    dbus_message_iter_open_container(&entry, DBUS_TYPE_VARIANT, "ay", &variant);
    dbus_message_iter_open_container(&variant, DBUS_TYPE_ARRAY, "y", &array);
    dbus_message_iter_append_fixed_array(&array, DBUS_TYPE_BYTE, &data, len);
    dbus_message_iter_close_container(&variant, &array);
    dbus_message_iter_close_container(&entry, &variant);
    
    dbus_message_iter_close_container(iter, &entry);
}
