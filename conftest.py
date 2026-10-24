from pathlib import Path

import pytest

# Runs before tests/conftest.py imports the integration, which needs the generated modules.
if not (Path(__file__).parent / "custom_components/ha_govee_led_ble/generated_protocol").is_dir():
    pytest.exit("generated_protocol is missing; run `make protocol` first", returncode=4)
