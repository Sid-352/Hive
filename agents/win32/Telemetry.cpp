#include "HiveCore.hpp"
#include <ctime>
#include <iomanip>
#include <iostream>
#include <windows.h>
#include <string.h>

void log_message(const char *level, const char *message) {
  if (strcmp(level, "DEBUG") == 0 && !g_debug_mode) {
    return;
  }

  std::time_t now = std::time(nullptr);
  char timestamp[32];
  std::strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S",
                std::localtime(&now));

  std::cerr << "[" << timestamp << "] [" << level << "] " << message
            << std::endl;
}

#define LOG_INFO(msg) log_message("INFO", msg)
#define LOG_ERROR(msg) log_message("ERROR", msg)
#define LOG_DEBUG(msg) log_message("DEBUG", msg)

bool is_on_ac_power() {
  SYSTEM_POWER_STATUS power_status;
  if (!GetSystemPowerStatus(&power_status)) {
    return true;
  }

  bool on_ac_power = (power_status.ACLineStatus != 0);
  return on_ac_power;
}

int get_ram_gb() {
  MEMORYSTATUSEX memory_status;
  memory_status.dwLength = sizeof(memory_status);

  if (!GlobalMemoryStatusEx(&memory_status)) {
    return 0;
  }

  int ram_gb =
      static_cast<int>(memory_status.ullTotalPhys / (1024ULL * 1024ULL * 1024ULL));

  char log_buf[64];
  sprintf_s(log_buf, "Telemetry: RAM = %d GB", ram_gb);
  LOG_INFO(log_buf);

  return ram_gb;
}

int get_logical_cores() {
  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);

  int logical_cores = static_cast<int>(system_info.dwNumberOfProcessors);

  char log_buf[64];
  sprintf_s(log_buf, "Telemetry: Logical cores = %d", logical_cores);
  LOG_INFO(log_buf);

  return logical_cores;
}

int get_vitality_score() {
  int vitality_score = 50;

  bool on_ac_power = is_on_ac_power();
  vitality_score += on_ac_power ? 50 : -20;

  int ram_gb = get_ram_gb();
  if (ram_gb > 8)
    vitality_score += 15;
  if (ram_gb > 16)
    vitality_score += 15;

  int logical_cores = get_logical_cores();
  if (logical_cores > 6)
    vitality_score += 20;

  char log_buf[128];
  sprintf_s(log_buf,
            "Telemetry: Vitality score = %d (AC:%d, RAM:%dGB, Cores:%d)", vitality_score,
            on_ac_power, ram_gb, logical_cores);
  LOG_INFO(log_buf);

  return vitality_score;
}

#ifdef UNIT_TEST
int main() {
  std::cout << "=== Telemetry Unit Tests ===\n\n";

  std::cout << "Test 1: Power Status\n";
  bool ac = is_on_ac_power();
  std::cout << "Result: " << (ac ? "AC Power" : "Battery") << "\n\n";

  std::cout << "Test 2: RAM\n";
  int ram = get_ram_gb();
  std::cout << "Result: " << ram << " GB\n\n";

  std::cout << "Test 3: CPU cores\n";
  int cores = get_logical_cores();
  std::cout << "Result: " << cores << " cores\n\n";

  std::cout << "Test 4: Vitality Score\n";
  int score = get_vitality_score();
  std::cout << "Result: " << score << "\n\n";

  std::cout << "=== Validation ===\n";
  std::cout << (ram > 0 ? "✓" : "✗") << " RAM > 0\n";
  std::cout << (cores > 0 ? "✓" : "✗") << " Cores > 0\n";
  std::cout << (score >= 30 && score <= 200 ? "✓" : "✗")
            << " Score in reasonable range\n";

  return 0;
}
#endif
