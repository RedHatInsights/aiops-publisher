import json
import requests
from wsgi import application, VERSION

# R0201 = Method could be a function Used when a method doesn't use its bound
# instance, and so could be written as a function.
# R0903 = Too few public methods

# pylint: disable=R0201,R0903


class TestRoot:
    """Test various use cases for the index route."""

    def test_route_with_upload_service_present(self, mocker):
        """Test index route when upload service is present."""
        client = application.test_client(mocker)

        url = '/'

        upload_response = {'status_code': 200}
        mocker.patch('wsgi._retryable', side_effect=upload_response)

        response = client.get(url)

        output = {
            "message": "Up and Running",
            "status": "OK",
            "version": VERSION
        }
        assert json.loads(response.get_data()) == output
        assert response.status_code == 200

    def test_route_with_upload_service_error(self, mocker):
        """Test index route when upload service has an error."""
        client = application.test_client(mocker)

        url = '/'

        upload_response = requests.HTTPError(
            mocker.Mock(status=404),
            'not found'
        )
        mocker.patch('wsgi._retryable', side_effect=upload_response)

        response = client.get(url)

        output = {
            "message": "upload-service not operational",
            "status": "Error",
            "version": VERSION
        }
        assert json.loads(response.get_data()) == output
        assert response.status_code == 500

    def test_route_with_upload_service_absent(self, mocker):
        """Test index route when upload service is absent."""
        client = application.test_client(mocker)

        url = '/'

        response = client.get(url)

        output = {
            "message": "upload-service not operational",
            "status": "Error",
            "version": VERSION
        }
        assert json.loads(response.get_data()) == output
        assert response.status_code == 500


def test_get_route_for_publish(mocker):
    """Test GET Publish route."""
    client = application.test_client(mocker)

    url = '/api/v0/publish'

    response = client.get(url)

    output = {
        "message": "Requires a POST call to publish recommendations",
        "status": "OK",
        "version": VERSION
    }
    assert json.loads(response.get_data()) == output
    assert response.status_code == 200
