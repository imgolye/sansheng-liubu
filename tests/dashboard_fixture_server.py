import argparse
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

from dashboard_test_support import create_fixture_openclaw_dir, patched_openclaw_path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "templates" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import collaboration_dashboard  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18930)
    parser.add_argument("--frontend-dist", default=str(ROOT / "frontend" / "dist"))
    args = parser.parse_args()

    tmpdir = tempfile.TemporaryDirectory(prefix="sansheng-e2e-")
    openclaw_dir = create_fixture_openclaw_dir(tmpdir.name)
    stop_event = threading.Event()

    def handle_stop(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    with patched_openclaw_path(openclaw_dir):
        server = collaboration_dashboard.ThreadingHTTPServer(("127.0.0.1", args.port), collaboration_dashboard.CollaborationDashboardHandler)
        server.openclaw_dir = openclaw_dir
        server.output_dir = openclaw_dir / "dashboard"
        server.live_interval = 0.2
        server.dashboard_auth_token = collaboration_dashboard.resolve_dashboard_auth_token(openclaw_dir)
        server.frontend_dist = collaboration_dashboard.resolve_frontend_dist(openclaw_dir, explicit_path=args.frontend_dist)
        server.cors_origins = collaboration_dashboard.parse_cors_origins(",".join(sorted(collaboration_dashboard.DEFAULT_FRONTEND_ORIGINS)))
        collaboration_dashboard.build_dashboard_bundle(openclaw_dir, server.output_dir)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            while not stop_event.is_set():
                time.sleep(0.2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            tmpdir.cleanup()


if __name__ == "__main__":
    main()
