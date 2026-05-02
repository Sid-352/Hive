import argparse
import os
import shutil
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description="Hive Build Script")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-agent", action="store_true")
    parser.add_argument("--recompile-c", action="store_true")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(repo_root)

    print("[1/5] Syncing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "pytest"], check=True)

    if not args.skip_tests:
        print("[2/5] Running tests...")
        subprocess.run([sys.executable, "-m", "pytest"], check=True)

    if not args.skip_agent:
        print("[3/5] Building hardware agent...")
        if sys.platform == "win32":
            script = os.path.join(repo_root, "agents", "win32", "build.bat")
            subprocess.run([script, "--no-pause"], check=True, cwd=os.path.join(repo_root, "agents", "win32"))
        else:
            script = os.path.join(repo_root, "agents", "linux", "build.sh")
            subprocess.run(["bash", script], check=True, cwd=os.path.join(repo_root, "agents", "linux"))

    print("[4/5] Compiling standalone bundles...")
    base_cmd = [
        sys.executable, "-m", "nuitka", "--standalone", "--plugin-enable=pyside6",
        "--output-dir=dist", "--remove-output", "--assume-yes-for-downloads",
    ]
    if sys.platform == "win32":
        base_cmd.extend(["--windows-console-mode=force", "--windows-icon-from-ico=app/assets/Hive.ico", "--include-windows-runtime-dlls=yes"])
    if args.recompile_c: base_cmd.append("--clean-cache")

    data_files = [
        ("agents/shared/protocol.json", "agents/shared/protocol.json"),
        ("agents/shared/constants.hpp", "agents/shared/constants.hpp"),
        ("app/assets/fonts/Pacifico-Regular.ttf", "app/assets/fonts/Pacifico-Regular.ttf"),
        ("app/assets/Hive.ico", "app/assets/Hive.ico"),
        ("app/assets/HiveBee.png", "app/assets/HiveBee.png"),
    ]
    if sys.platform == "win32": data_files.append(("agents/win32/HiveAgent.exe", "agents/win32/HiveAgent.exe"))
    else:
        data_files.append(("agents/linux/HiveAgent", "agents/linux/HiveAgent"))
        data_files.append(("agents/linux/hive-wifidirect.conf", "agents/linux/hive-wifidirect.conf"))
    for src, dest in data_files: base_cmd.append(f"--include-data-file={src}={dest}")

    subprocess.run(base_cmd + ["--output-filename=Hive", "app/main.py"], check=True)
    subprocess.run(base_cmd + ["--output-filename=HiveHeadless", "app/headless.py"], check=True)

    dist_dir = os.path.join(repo_root, "dist")
    bundle_root = os.path.join(dist_dir, "Hive")
    if os.path.exists(bundle_root): shutil.rmtree(bundle_root)
    
    os.rename(os.path.join(dist_dir, "main.dist"), bundle_root)
    for name in ["main.exe", "main", "main.bin"]:
        path = os.path.join(bundle_root, name)
        if os.path.exists(path):
            os.rename(path, os.path.join(bundle_root, "Hive.exe" if sys.platform == "win32" else "Hive")); break

    h_src = os.path.join(dist_dir, "headless.dist")
    h_exe = "HiveHeadless.exe" if sys.platform == "win32" else "HiveHeadless"
    for name in [h_exe, "main.exe", "main"]:
        path = os.path.join(h_src, name)
        if os.path.exists(path): shutil.copy2(path, os.path.join(bundle_root, h_exe)); break
    shutil.rmtree(h_src)

    print("[5/5] Finalizing release...")
    tools = ["setup-hive.ps1", "remove-hive.ps1"] if sys.platform == "win32" else ["setup-hive.sh", "remove-hive.sh"]
    for t in tools: shutil.copy2(os.path.join("dist_tools", t), os.path.join(bundle_root, t))
    if sys.platform != "win32":
        shutil.copy2("agents/linux/hive-wifidirect.conf", os.path.join(bundle_root, "hive-wifidirect.conf"))
        for t in tools: os.chmod(os.path.join(bundle_root, t), 0o755)

    print(f"\n[SUCCESS] Release ready at: {bundle_root}")

if __name__ == "__main__":
    main()
