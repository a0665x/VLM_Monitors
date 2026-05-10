import logging
from typing import Optional, Dict, Any
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import httpx

logger = logging.getLogger(__name__)

class TwilioNotifier:
    def __init__(self):
        self.client: Optional[Client] = None
        self.from_number: Optional[str] = None
        self.webhook_url: Optional[str] = None
        self.is_active = False

    def configure(self, account_sid: str, auth_token: str, from_number: str, webhook_url: str = "") -> bool:
        """Configures the Twilio client and webhook. Returns True if successful (credentials look valid format)."""
        try:
            self.webhook_url = webhook_url
            
            # If Twilio credentials are provided, configure Client
            if account_sid and auth_token and from_number:
                self.client = Client(account_sid, auth_token)
                self.from_number = from_number
                self.is_active = True
                logger.info(f"Twilio configured with Account SID: {account_sid[:4]}... and From: {from_number}")
            else:
                self.is_active = False
                if webhook_url:
                    logger.info(f"Webhook configured: {webhook_url}")
                    return True # Valid if at least webhook is set
                logger.warning("Twilio configuration missing fields and no webhook provided.")
                return False
            
            if webhook_url:
                logger.info(f"Webhook configured: {webhook_url}")

            return True
        except Exception as e:
            logger.error(f"Failed to configure Notifier: {e}")
            self.is_active = False
            return False

    async def send_sms(self, to_number: str, message: str) -> bool:
        """Sends an SMS to the specified number asynchronously."""
        if not self.is_active or not self.client:
            # Not an error if only webhook is used, but return False for SMS status
            return False

        import asyncio
        try:
            logger.info(f"Sending SMS to {to_number}: {message}")
            # Run blocking Twilio call in a separate thread
            def _send():
                return self.client.messages.create(
                    body=message,
                    from_=self.from_number,
                    to=to_number
                )
            
            msg = await asyncio.to_thread(_send)
            logger.info(f"SMS sent successfully. SID: {msg.sid}")
            return True
        except TwilioRestException as e:
            logger.error(f"Twilio Error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {e}")
            return False

    async def send_webhook(self, data: Dict[str, Any]) -> bool:
        """Sends a POST request to the configured webhook asynchronously."""
        if not self.webhook_url:
            return False
        
        try:
            logger.info(f"Sending webhook to {self.webhook_url}")
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=data, timeout=5.0)
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info("Webhook sent successfully.")
                return True
            else:
                logger.error(f"Webhook failed with status: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            return False

    def is_configured(self) -> bool:
        return self.is_active or bool(self.webhook_url)
