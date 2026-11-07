"""
Ordinary tests must never reach a real model, even though Ollama is the default provider
and may be running on the developer's machine. Tests that exercise the adapter inject a
mock transport. test_ollama_live.py is the one explicit, opt-in exception.
"""
import os

os.environ["BIOS_LLM_PROVIDER"] = "deterministic"


def pytest_configure(config):
    config.addinivalue_line("markers", "live_ollama: runs real inference; needs BIOS_RUN_LIVE_OLLAMA=1")
