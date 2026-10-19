import hashlib
import json
import os
from pathlib import Path
import re

def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main():
    config = json.loads(os.environ["LYRA_BASELINE_PROBE_CONFIG"])
    report = {"schema_version": 1, "probe": "real_lyra_baseline_load",
              "status": "running", "executed_in_real_unreal": False,
              "engine_version": None, "project_directory": None,
              "process_id": os.getpid(), "effective_uid": os.geteuid(),
              "executable": os.path.realpath("/proc/self/exe"),
              "native_class": None, "loaded_modules": {}, "assets": [],
              "boundary": "Actual baseline module/asset loading only. No save, gameplay, Experience activation, visual/audio acceptance, or score."}
    with open(config["output"], "x", encoding="utf-8") as stream:
        def checkpoint():
            stream.seek(0)
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.truncate()
            stream.flush()
        checkpoint()
        try:
            import unreal
            if os.geteuid() == 0:
                raise RuntimeError("Unreal must run as non-root")
            report["engine_version"] = str(unreal.SystemLibrary.get_engine_version())
            report["raw_project_directory"] = str(unreal.SystemLibrary.get_project_directory())
            if not report["raw_project_directory"].strip():
                raise RuntimeError("Unreal returned an empty project directory")
            report["project_directory"] = str(Path(report["raw_project_directory"]).resolve())
            if not re.match(r"^5\.8\.3(?:[-+ ]|$)", report["engine_version"]):
                raise RuntimeError("Unexpected actual engine version")
            if Path(report["project_directory"]).resolve() != Path(config["project_directory"]).resolve():
                raise RuntimeError("Unreal loaded a different project directory")
            if report["executable"] != os.path.realpath(config["editor"]):
                raise RuntimeError("Unexpected actual UE executable")
            native_class = unreal.load_class(None, config["native_class"])
            if native_class is None:
                raise RuntimeError("Lyra interaction native class failed to load")
            report["native_class"] = str(native_class.get_path_name())
            checkpoint()
            maps = Path("/proc/self/maps").read_text(encoding="utf-8")
            for name, expected in config["modules"].items():
                mapped = []
                for line in maps.splitlines():
                    parts = line.split(None, 5)
                    if len(parts) != 6 or "x" not in parts[1] or not parts[5].startswith("/"):
                        continue
                    path = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), parts[5])
                    if path.endswith(" (deleted)"):
                        continue
                    if os.path.realpath(path) == expected["path"]:
                        mapped.append(line)
                if not mapped:
                    raise RuntimeError("Project module has no executable mapping: " + name)
                actual_hash = digest_file(expected["path"])
                report["loaded_modules"][name] = {"path": expected["path"],
                                                   "sha256": actual_hash,
                                                   "executable_mapping_lines": mapped}
                if actual_hash != expected["sha256"]:
                    raise RuntimeError("Project module changed during probe: " + name)
                checkpoint()
            for asset_path in config["assets"]:
                asset = unreal.load_object(None, asset_path)
                if asset is None:
                    raise RuntimeError("Asset failed to load: " + asset_path)
                report["assets"].append({"requested_path": asset_path,
                                         "loaded_path": str(asset.get_path_name()),
                                         "class": str(asset.get_class().get_name())})
                checkpoint()
            report["status"] = "completed"
            report["executed_in_real_unreal"] = True
        except BaseException as error:
            report["status"] = "failed"
            report["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            checkpoint()
    print("LYRA_BASELINE_PROBE_COMPLETED " + config["output"])

if __name__ == "__main__":
    main()
