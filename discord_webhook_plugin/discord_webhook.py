import threading
import time
import db
import datetime
import re
import requests
from logger import get_logger

# Get logger for this module
logger = get_logger(__name__)


class DiscordWebhook:
    def __init__(self, queue):
        self.queue = queue
        self.webhook_url = db.get_parameter("discord_webhook_url")
        
        # Start thread to check queue
        self.thread = threading.Thread(target=self.run_check_queue)
        self.thread.daemon = True
        self.thread.start()

    def run_check_queue(self):
        while True:
            try:
                self.check_discord_queue()
                time.sleep(0.1)  # Small sleep to prevent high CPU usage
            except Exception as e:
                logger.error(f"Error checking Discord queue: {str(e)}", exc_info=True)

    def check_discord_queue(self):
        if not self.queue.empty():
            try:
                content, url, text, buy_url, buy_text = self.queue.get()
                # Send item to Discord
                self.send_notification(content, url)
            except Exception as e:
                logger.error(
                    f"Error processing item for Discord webhook: {str(e)}", exc_info=True
                )

    def parse_content(self, content):
        """
        Parse the formatted content to extract title, brand, price, and image.
        
        Returns:
            dict: Dictionary with 'title', 'brand', 'price', 'image' keys
        """
        parsed = {
            'title': '',
            'brand': '',
            'price': '',
            'image': ''
        }
        
        try:
            # Extract title (🆕 Title : {title})
            title_match = re.search(r'🆕\s*Title\s*:\s*(.+?)(?:\n|$)', content)
            if title_match:
                parsed['title'] = title_match.group(1).strip()
            else:
                # Fallback: try to extract any text before first newline or emoji
                first_line = content.split('\n')[0].strip()
                if first_line and not first_line.startswith('🆕'):
                    parsed['title'] = first_line
            
            # Extract brand (🛍️ Brand : {brand})
            brand_match = re.search(r'🛍️\s*Brand\s*:\s*(.+?)(?:\n|$)', content)
            if brand_match:
                parsed['brand'] = brand_match.group(1).strip()
            
            # Extract price (💶 Price : {price})
            price_match = re.search(r'💶\s*Price\s*:\s*(.+?)(?:\n|$)', content)
            if price_match:
                parsed['price'] = price_match.group(1).strip()
            
            # Extract image link (<a href="{image}">)
            image_match = re.search(r'<a\s+href=["\']([^"\']+)["\']', content)
            if image_match:
                parsed['image'] = image_match.group(1)
        except Exception as e:
            logger.debug(f"Error parsing content: {e}")
        
        return parsed

    def create_embed(self, title, brand, price, image_url, item_url):
        """
        Create a Discord embed for a Vinted item.
        Format: Title (as embed title with link), Price, Brand (in description)
        
        Returns:
            dict: Discord embed object
        """
        # Build description with Price and Brand (matching RSS feed format)
        description_lines = []
        
        if price:
            description_lines.append(price)
        if brand:
            description_lines.append(brand)
        
        embed = {
            "title": title or "Vinted Item",
            "url": item_url,  # Makes the title clickable
            "description": "\n".join(description_lines) if description_lines else "",
            "color": 0x00ff00,  # Green color
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "footer": {
                "text": "Vinted Notifications"
            }
        }
        
        # Add image if available
        if image_url:
            embed["image"] = {
                "url": image_url
            }
        
        return embed

    def send_notification(self, content, url):
        """
        Send a notification to Discord via webhook.
        
        Args:
            content (str): The formatted content string
            url (str): The Vinted item URL
        """
        # Check if webhook URL is configured
        webhook_url = db.get_parameter("discord_webhook_url")
        if not webhook_url:
            logger.debug("Discord webhook URL not configured, skipping notification")
            return
        
        try:
            # Parse content to extract item details
            parsed = self.parse_content(content)
            title = parsed['title'] or "Vinted Item"
            
            # Create embed
            embed = self.create_embed(
                title=title,
                brand=parsed['brand'],
                price=parsed['price'],
                image_url=parsed['image'],
                item_url=url
            )
            
            # Prepare payload
            payload = {
                "embeds": [embed],
                "username": "Vinted Notifications"
            }
            
            # Send webhook request
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            logger.debug(f"Discord notification sent successfully for: {title}")
            
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Error sending Discord webhook: {str(e)}. "
                f"Response: {e.response.text if hasattr(e, 'response') and e.response else 'No response'}"
            )
        except Exception as e:
            logger.error(f"Error formatting Discord notification: {str(e)}", exc_info=True)


def discord_webhook_process(queue):
    """
    Process function for the Discord webhook.
    
    Args:
        queue (Queue): The queue to get new items from
    """
    logger.info("Discord webhook process started")
    try:
        webhook = DiscordWebhook(queue)
        # Keep the process running
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Discord webhook process stopped")
    except Exception as e:
        logger.error(f"Error in Discord webhook process: {e}", exc_info=True)
