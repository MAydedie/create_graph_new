import importlib.util
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("create_graph_live_app", ROOT / "app.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

app = module.create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5003, debug=False, use_reloader=False)
