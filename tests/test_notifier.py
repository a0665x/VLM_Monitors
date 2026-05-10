import unittest
from unittest.mock import MagicMock, patch
from src.services.notifier import TwilioNotifier

class TestTwilioNotifier(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.notifier = TwilioNotifier()

    def test_configure_success(self):
        with patch('src.services.notifier.Client') as MockClient:
            result = self.notifier.configure("AC123", "token", "+123")
            self.assertTrue(result)
            self.assertTrue(self.notifier.is_configured())
            MockClient.assert_called_with("AC123", "token")

    def test_configure_fail_missing_args(self):
        result = self.notifier.configure("", "token", "+123")
        self.assertFalse(result)
        self.assertFalse(self.notifier.is_configured())

    async def test_send_sms_success(self):
        with patch('src.services.notifier.Client') as MockClient:
            mock_client_instance = MockClient.return_value
            mock_messages = mock_client_instance.messages
            mock_create = mock_messages.create
            mock_create.return_value.sid = "SM123"

            self.notifier.configure("AC123", "token", "+123")
            result = await self.notifier.send_sms("+456", "Test Message")
            
            self.assertTrue(result)
            # Since it runs in a thread, we verify the mock was called
            mock_create.assert_called_with(
                body="Test Message",
                from_="+123",
                to="+456"
            )

    async def test_send_sms_not_configured(self):
        result = await self.notifier.send_sms("+456", "Test Message")
        self.assertFalse(result)

    async def test_webhook_success(self):
        with patch('src.services.notifier.httpx.AsyncClient') as MockClient:
            mock_instance = MockClient.return_value.__aenter__.return_value
            mock_instance.post.return_value.status_code = 200
            
            self.notifier.configure("", "", "", webhook_url="http://test.com")
            result = await self.notifier.send_webhook({"test": "data"})
            
            self.assertTrue(result)
            mock_instance.post.assert_called_with("http://test.com", json={"test": "data"}, timeout=5.0)

    async def test_webhook_fail(self):
        with patch('src.services.notifier.httpx.AsyncClient') as MockClient:
            mock_instance = MockClient.return_value.__aenter__.return_value
            mock_instance.post.return_value.status_code = 500
            
            self.notifier.configure("", "", "", webhook_url="http://test.com")
            result = await self.notifier.send_webhook({"test": "data"})
            
            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
