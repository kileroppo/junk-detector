"""Tests for the Python SDK (sdk/python/jianzhen_client.py)."""
from unittest.mock import patch, MagicMock

from sdk.python.jianzhen_client import JianzhenClient


class TestJianzhenClient:
    """Tests for JianzhenClient class."""

    def test_client_initialization_default(self):
        """Client should initialize with default localhost URL."""
        client = JianzhenClient()
        assert client.base_url == "http://localhost:8000"
        assert client.timeout == 30.0

    def test_client_initialization_custom(self):
        """Client should accept custom base_url and api_key."""
        client = JianzhenClient(api_key="test-key", base_url="http://api.example.com")
        assert client.base_url == "http://api.example.com"
        assert "X-API-Key" in client._headers
        assert client._headers["X-API-Key"] == "test-key"

    def test_client_has_score_method(self):
        """Client should have a score() method."""
        client = JianzhenClient()
        assert hasattr(client, "score")
        assert callable(client.score)

    def test_client_has_score_url_method(self):
        """Client should have a score_url() method."""
        client = JianzhenClient()
        assert hasattr(client, "score_url")
        assert callable(client.score_url)

    def test_client_has_health_method(self):
        """Client should have a health() method."""
        client = JianzhenClient()
        assert hasattr(client, "health")
        assert callable(client.health)

    def test_client_has_demo_method(self):
        """Client should have a demo() method."""
        client = JianzhenClient()
        assert hasattr(client, "demo")
        assert callable(client.demo)

    def test_base_url_strips_trailing_slash(self):
        """Base URL should have trailing slash stripped."""
        client = JianzhenClient(base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"

    @patch("sdk.python.jianzhen_client.httpx.Client")
    def test_score_sends_post_to_score_endpoint(self, mock_client_cls):
        """score() should POST to /score with text payload."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"overall_score": 75}
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        client = JianzhenClient()
        result = client.score("test text")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/score" in call_args[0][0] or "/score" in str(call_args)

    @patch("sdk.python.jianzhen_client.httpx.Client")
    def test_health_sends_get_to_health_endpoint(self, mock_client_cls):
        """health() should GET /health."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        client = JianzhenClient()
        result = client.health()

        mock_client.get.assert_called_once()
