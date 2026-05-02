#ifndef HIVE_CONSTANTS_HPP
#define HIVE_CONSTANTS_HPP

namespace Hive {
    const char* const AGENT_VERSION = "1.1.0";
    const char* const PROTOCOL_VERSION = "1.5";

    const uint32_t BZZZ_MAGIC = 0x425A5A5A;
    const char* const SERVICE_UUID = "00000001-4856-4147-454E-540000000001";
    const char* const SSID_PREFIX = "DIRECT-HV-";
    const char* const DEFAULT_PASSPHRASE = "Hive12345678";

    const char* const RESTORE_FILE = ".hive_restore.json";

    const char* const DATA_PIPE_WIN_BASE = "\\\\.\\pipe\\hive_data_";
    const char* const DATA_SOCKET_LINUX_BASE = "/tmp/hive_";

    const int DEFAULT_SCAN_DURATION = 5;
    const int MAX_IP_POLL_ATTEMPTS = 50;
    const int IP_POLL_INTERVAL_MS = 200;
}

#endif
