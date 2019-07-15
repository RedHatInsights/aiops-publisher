import os
import tarfile
import requests

import pytest

import wsgi

# R0201 = Method could be a function Used when a method doesn't use its bound
# instance, and so could be written as a function.
# R0903 = Too few public methods
# W0212 = Access to a protected member of a client class

# pylint: disable=R0201,R0903,W0212


class TestRetryable:
    """Test suite for `wsgi._retryable`."""

    @pytest.fixture(autouse=True)
    def default_setup(self, mocker):
        """Set mock for session and response before every test run."""
        # pylama: ignore=W0201
        session_cls = mocker.patch.object(requests, 'Session')
        self.session = mocker.MagicMock()
        self.session.__enter__.return_value = self.session
        session_cls.return_value = self.session

        self.response = mocker.Mock()
        response_cls = mocker.patch.object(requests, 'Response')
        response_cls.return_value = self.response
        self.session.get.return_value = self.response
        self.session.post.return_value = self.response

    def test_response(self):
        """Test a response can be received."""
        resp = wsgi._retryable('get', 'http://some.thing')

        self.session.get.assert_called_once_with('http://some.thing')
        assert resp == self.response

    @pytest.mark.parametrize('method', ('get', 'GET', 'post', 'POST'))
    def test_method_selection(self, method):
        """Test method selection propagation."""
        wsgi._retryable(method, 'http://some.thing')

        getattr(self.session, method).assert_called_once_with(
            'http://some.thing'
        )

    def test_retry(self):
        """Should retry when first request fails."""
        self.response.raise_for_status.side_effect = \
            [requests.HTTPError(), None]

        wsgi._retryable('get', 'http://some.thing')

        assert self.session.get.call_count == 2

    def test_retry_failed(self):
        """Should retry as many as MAX_RETRIES."""
        self.response.raise_for_status.side_effect = requests.HTTPError()

        with pytest.raises(requests.HTTPError):
            wsgi._retryable('get', 'http://some.thing')

        assert self.session.get.call_count == wsgi.MAX_RETRIES
        assert wsgi.MAX_RETRIES > 1


class TestGetRoot:
    """Test various use cases for the index route."""

    def test_route_with_upload_service_present(self, mocker):
        """Test index route when upload service is present."""
        client = wsgi.application.test_client(mocker)

        url = '/'

        upload_response = {'status_code': 200}
        mocker.patch('wsgi._retryable', side_effect=upload_response)

        response = client.get(url)

        output = {
            "message": "Up and Running",
            "status": "OK",
            "version": wsgi.VERSION
        }
        assert response.get_json() == output
        assert response.status_code == 200

    def test_route_with_upload_service_error(self, mocker):
        """Test index route when upload service has an error."""
        client = wsgi.application.test_client(mocker)

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
            "version": wsgi.VERSION
        }
        assert response.get_json() == output
        assert response.status_code == 500

    def test_route_with_upload_service_absent(self, mocker):
        """Test index route when upload service is absent."""
        client = wsgi.application.test_client(mocker)

        url = '/'

        response = client.get(url)

        output = {
            "message": "upload-service not operational",
            "status": "Error",
            "version": wsgi.VERSION
        }
        assert response.get_json() == output
        assert response.status_code == 500


def test_get_publish(mocker):
    """Test GET Publish route."""
    client = wsgi.application.test_client(mocker)

    url = '/api/v0/publish'

    response = client.get(url)

    output = {
        "message": "Requires a POST call to publish recommendations",
        "status": "OK",
        "version": wsgi.VERSION
    }
    assert response.get_json() == output
    assert response.status_code == 200


def test_get_version(mocker):
    """Test GET Publish route."""
    client = wsgi.application.test_client(mocker)

    url = '/api/v0/version'

    response = client.get(url)

    output = {
        "message": f"AIOPS Publisher Version {wsgi.VERSION}",
        "status": "OK",
        "version": wsgi.VERSION
    }
    assert response.get_json() == output
    assert response.status_code == 200


class TestPostPublish:
    """Test suite for `wsgi.post_publish`."""

    @pytest.fixture(autouse=True)
    def default_setup(self, mocker):
        """Set mocker and test server client before every test run."""
        # pylama: ignore=W0201
        self.url = '/api/v0/publish'
        self.client = wsgi.application.test_client()
        self._retryable = mocker.patch.object(wsgi, '_retryable')

    def test_post(self):
        """Test successfull post."""
        payload = dict(id="stub_id", data={"some": "data"}, ai_service='x')
        headers = {'x-rh-identity': 'ABC'}
        resp = self.client.post(self.url, json=payload, headers=headers)

        assert resp.status_code == 200
        assert resp.get_json() == {
            'status': 'OK',
            'message': 'Data published via Upload service'
        }

    @pytest.mark.parametrize('data,errors', (
        (dict(id="stub_id", data={"some": "data"}), ()),
        (dict(id="stub_id", data={"some": "data"}, ai_service="ai"), ()),
        (dict(id="stub_id"), ('data',)),
        (dict(data={"some": "data"}), ('id',)),
        ({}, ('id', 'data')),
        (dict(id="stub_id", data={"some": "data"}, extra="field"), ()),
    ))
    def test_input_schema(self, data, errors):
        """Validate request payload scheme."""
        resp = self.client.post(self.url, json=data)

        if not errors:
            assert resp.status_code == 200
            assert resp.get_json() == {
                'status': 'OK',
                'message': 'Data published via Upload service',
            }
        else:
            assert resp.status_code == 400
            assert resp.get_json() == {
                'status': 'Error',
                'message': 'Input payload validation failed',
                'errors': {
                    k: ['Missing data for required field.'] for k in errors
                },
            }

    def test_unable_to_create_tmp_file(self, mocker):
        """Failure to create tmp file should result in 500."""
        mocker.patch(
            'tempfile.NamedTemporaryFile', side_effect=IOError('Fail')
        )

        payload = dict(id="stub_id", data={"some": "data"})
        resp = self.client.post(self.url, json=payload)

        assert resp.status_code == 500
        assert resp.get_json() == {
            'status': 'Error',
            'type': 'OSError',
            'message': 'Error during TAR.GZ creation: Fail'
        }

    def test_unable_to_dump_tar_tmp_file(self, mocker):
        """Failure to dump data to tmp file should result in 500."""
        tar_file = mocker.MagicMock(name='tmp.tar')
        tar_file.addfile.side_effect = tarfile.TarError('Fail')

        tar_context = mocker.patch.object(tarfile, 'open')
        tar_context.return_value = tar_context
        tar_context.__enter__.return_value = tar_file

        payload = dict(id="stub_id", data={"some": "data"})
        resp = self.client.post(self.url, json=payload)

        assert resp.status_code == 500
        assert resp.get_json() == {
            'status': 'Error',
            'type': 'TarError',
            'message': 'Error during TAR.GZ creation: Fail'
        }

    def test_headers_for_upload_service(self, mocker):
        """Should pass headers to upload service."""
        payload = dict(id="stub_id", data={"some": "data"})
        headers = {'x-rh-identity': 'ABC'}
        self.client.post(self.url, json=payload, headers=headers)

        headers = {
            'x-rh-insights-request-id': 'stub_id',
            'x-rh-identity': 'ABC'
        }
        self._retryable.assert_called_once_with(
            'post',
            'http://upload:8080/api/ingress/v1/upload',
            files=mocker.ANY,
            headers=headers
        )

    def test_files_for_upload_service(self, mocker):
        """Should pass headers to upload service."""
        payload = dict(id="stub_id", data={"some": "data"}, ai_service='x')
        headers = {'x-rh-identity': 'ABC'}
        self.client.post(self.url, json=payload, headers=headers)

        files = {
            'upload': (
                mocker.ANY, mocker.ANY,
                'application/vnd.redhat.x.aiservice+tgz'
            )
        }
        self._retryable.assert_called_once_with(
            'post',
            'http://upload:8080/api/ingress/v1/upload',
            files=files,
            headers=mocker.ANY
        )

    def test_tmp_file_content(self, mocker):
        """Ensure data are saved in tmp TAR file properly."""
        payload = dict(id="B", data={"some": "data"}, ai_service='A')
        headers = {'x-rh-identity': 'ABC'}

        with mocker.mock_module.patch.object(os, 'remove') as mock:
            self.client.post(self.url, json=payload, headers=headers)
            filename = mock.call_args[0][0]

        with tarfile.open(filename, 'r:gz') as tar:
            content = tar.extractfile('A_B.json').read()
            assert content == b'{"some": "data"}'

        os.remove(filename)

    def test_default_ai_service_name(self, mocker):
        """If `ai_service` is not set, it should use a default value."""
        payload = dict(id="stub_id", data={"some": "data"})
        self.client.post(self.url, json=payload)

        files = {
            'upload': (
                mocker.ANY, mocker.ANY,
                'application/vnd.redhat.generic_ai.aiservice+tgz'
            )
        }
        self._retryable.assert_called_once_with(
            'post',
            'http://upload:8080/api/ingress/v1/upload',
            files=files,
            headers=mocker.ANY
        )

    def test_upload_service_unavailable(self):
        """Should fail when upload service is not available."""
        self._retryable.side_effect = requests.HTTPError('Fail')

        payload = dict(id="stub_id", data={"some": "data"})
        resp = self.client.post(self.url, json=payload)

        assert resp.status_code == 500
        assert resp.get_json() == {
            'status': 'Error',
            'type': 'HTTPError',
            'status_code': 500,
            'message': "Unable to access upload-service"
        }

    def test_cleanup_on_success(self, mocker):
        """Should remove tmp file when uploaded."""
        remove_spy = mocker.spy(os, 'remove')

        payload = dict(id="B", data={"some": "data"}, ai_service='A')
        headers = {'x-rh-identity': 'ABC'}
        self.client.post(self.url, json=payload, headers=headers)

        remove_spy.assert_called_once()

    def test_cleanup_on_failure_when_upload(self, mocker):
        """Should remove tmp file when upload fails."""
        remove_spy = mocker.spy(os, 'remove')
        self._retryable.side_effect = requests.HTTPError('Fail')

        payload = dict(id="B", data={"some": "data"}, ai_service='A')
        headers = {'x-rh-identity': 'ABC'}
        self.client.post(self.url, json=payload, headers=headers)

        remove_spy.assert_called_once()

    def test_cleanup_on_failure_when_preparing_file(self, mocker):
        """Should remove tmp file when preparation of TAR fails."""
        remove_spy = mocker.spy(os, 'remove')
        self._retryable.side_effect = requests.HTTPError('Fail')

        payload = dict(id="B", data={"some": "data"}, ai_service='A')
        headers = {'x-rh-identity': 'ABC'}
        self.client.post(self.url, json=payload, headers=headers)

        remove_spy.assert_called_once()
