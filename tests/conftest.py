from imp import reload
import pytest

import wsgi


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """Set up environment."""
    # Set Test variables
    monkeypatch.setenv('UPLOAD_SERVICE', 'http://upload:8080')
    monkeypatch.setenv('UPLOAD_SERVICE_PATH', 'api/ingress/v1')

    reload(wsgi)
