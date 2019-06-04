from imp import reload
import pytest

import wsgi


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """Set up environment."""
    # Set Test variables
    monkeypatch.setenv('UPLOAD_SERVICE_API', 'http://upload:8080')

    reload(wsgi)
