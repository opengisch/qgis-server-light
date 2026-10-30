import subprocess
import sys


def test_import_without_dependencies():
    # blocking the modules makes any import of them fail with ImportError
    code = (
        "import pkgutil\n"
        "import sys\n"
        "sys.modules['redis'] = None\n"
        "sys.modules['xsdata'] = None\n"
        "import qgis_server_light.interface as interface\n"
        "for module in pkgutil.walk_packages(interface.__path__, f'{interface.__name__}.'):\n"
        "    __import__(module.name)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
