"""Read-only diagnostic run by the real UE PythonScript commandlet.

LYRA_EDITOR_PROBE_OUTPUT must name a new absolute .json path. Optional editor
API checks only report Python symbol exposure; they do not test functionality.
"""

import os
import json


def api_presence(unreal_module, class_name, methods):
    exists = hasattr(unreal_module, class_name)
    owner = getattr(unreal_module, class_name) if exists else None
    return {
        "class_exposed": exists,
        "methods_exposed": {
            name: exists and hasattr(owner, name) for name in methods
        },
    }


def main():
    output = os.environ.get("LYRA_EDITOR_PROBE_OUTPUT", "").strip()
    if not output:
        raise RuntimeError("LYRA_EDITOR_PROBE_OUTPUT must name a new JSON output file.")
    if not os.path.isabs(output) or not output.lower().endswith(".json"):
        raise RuntimeError("LYRA_EDITOR_PROBE_OUTPUT must be an absolute .json path.")
    output = os.path.abspath(output)
    report = {
        "schema_version": 1,
        "probe": "real_ue_editor_python_api_presence",
        "status": "running",
        "executed_in_real_unreal": False,
        "engine_version": None,
        "required_engine_version_prefix": "5.8.3",
        "project_directory": None,
        "process_id": os.getpid(),
        "api_presence": {},
        "score": None,
        "boundary": (
            "Diagnostic only. Optional APIs are checked with hasattr, never called. "
            "A missing symbol can mean its plugin/module is not enabled or loaded. "
            "This does not compile a candidate, test feature behavior, or award a score. "
            "The script does not load, modify, or save project assets."
        ),
    }
    # Exclusive creation prevents stale success evidence or an accidental overwrite.
    # The initial record remains 'running' if UE terminates before completion.
    with open(output, "x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        try:
            import unreal

            report["api_presence"]["SystemLibrary"] = api_presence(
                unreal, "SystemLibrary", ("get_engine_version", "get_project_directory")
            )
            system = report["api_presence"]["SystemLibrary"]
            if not system["class_exposed"] or not all(system["methods_exposed"].values()):
                raise RuntimeError("Required Unreal SystemLibrary query APIs are unavailable.")
            # These two read-only calls are the only Unreal API invocations.
            report["engine_version"] = str(unreal.SystemLibrary.get_engine_version())
            project_directory = str(unreal.SystemLibrary.get_project_directory())
            if not report["engine_version"].startswith("5.8.3"):
                raise RuntimeError("Expected UE 5.8.3; found " + report["engine_version"])
            if not project_directory:
                raise RuntimeError("Unreal returned an empty project directory.")
            # Resolve in the real UE process: it can change its working directory
            # while initializing, and FPaths may return a relative project path.
            report["project_directory_raw"] = project_directory
            report["project_directory"] = os.path.abspath(project_directory)
            checks = {
                "PythonScriptLibrary": (
                    "is_python_available", "is_python_initialized", "execute_python_command"
                ),
                "BlueprintEditorLibrary": (
                    "find_graph", "list_graphs", "compile_blueprint",
                    "create_blueprint_asset_with_parent", "add_member_variable"
                ),
                "BlueprintGraphEditor": (
                    "get_graph_editor", "get_graph_editor_by_name", "create_and_edit_function_graph"
                ),
                "UMGToolSet": (
                    "get_widgets", "create_widget_blueprint", "add_widget", "compile_widget_blueprint"
                ),
            }
            for class_name, methods in checks.items():
                report["api_presence"][class_name] = api_presence(unreal, class_name, methods)
            report["status"] = "completed"
            report["executed_in_real_unreal"] = True
        except BaseException as error:
            report["status"] = "failed"
            report["executed_in_real_unreal"] = False
            report["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            stream.seek(0)
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.truncate()
            stream.flush()
    print("LYRA_EDITOR_PROBE_COMPLETED " + output)


if __name__ == "__main__":
    main()
