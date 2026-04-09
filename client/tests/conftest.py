import sys
from pathlib import Path

# Ensure client/agent/ is importable as the "agent" package
_client_dir = Path(__file__).resolve().parent.parent
_agent_dir = _client_dir / "agent"
if str(_agent_dir.parent) not in sys.path:
    sys.path.insert(0, str(_agent_dir.parent))
