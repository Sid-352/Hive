import asyncio
import os
import sys

import pytest

from app.core.agent import AsyncHardwareAgent


@pytest.mark.integration
def test_agent_start_and_shutdown_real_binary():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")

    if sys.platform != "win32":
        pytest.skip("This integration test currently targets win32 agent binary")

    exe_path = os.path.join("agents", "win32", "HiveAgent.exe")
    if not os.path.isfile(exe_path):
        pytest.skip("HiveAgent.exe not present")

    async def _run():
        agent = AsyncHardwareAgent()
        await agent.start()
        await agent.send_command({"type": "STATUS"})
        event = await asyncio.wait_for(agent.response_queue.get(), timeout=3.0)
        assert event.get("type") == "STATUS"
        await agent.stop()

    asyncio.run(_run())
