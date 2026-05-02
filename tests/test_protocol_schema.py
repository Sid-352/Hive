import json
from pathlib import Path


def test_protocol_schema_has_required_commands_and_responses():
    schema_path = Path("agents/shared/protocol.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    commands = schema.get("commands", {})
    responses = schema.get("responses", {})

    required_commands = {
        "STATUS",
        "GET_TELEMETRY",
        "SCAN",
        "CONNECT",
        "DISCONNECT",
        "CREATE_GROUP",
        "STOP_GROUP",
        "START_DATA_PLANE",
        "STOP_DATA_PLANE",
        "SHUTDOWN",
    }
    required_responses = {
        "STATUS",
        "TELEMETRY",
        "SCAN_RESULT",
        "CONNECTED",
        "GROUP_CREATED",
        "DATA_PLANE_STARTED",
        "ERROR",
    }

    assert required_commands.issubset(commands.keys())
    assert required_responses.issubset(responses.keys())


def test_protocol_status_states_match_expected_values():
    schema_path = Path("agents/shared/protocol.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    states = schema["responses"]["STATUS"]["fields"]["state"]["enum"]
    assert set(states) == {
        "READY",
        "DISCONNECTED",
        "SCANNING",
        "ASSOCIATING",
        "CONNECTED_AS_CLIENT",
        "CONNECTED_AS_GO",
    }
