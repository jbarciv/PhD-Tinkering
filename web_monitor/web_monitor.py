import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
import os
import datetime

URL = "theURLToCheck.com"
STATE_FILE = "./tmp/web_monitor_state.txt"  # Stores previous content snapshot

# SMTP Settings (from your existing script)
smtp_ssl_host = 'smtp.gmail.com'
smtp_ssl_port = 465
sender = 'senderEmail@gmail.com'
receiver = 'receiverEmail@gmail.com'
username = 'mailToCheck@gmail.com'
password = 'yourAppEmailPassword'  # Use your app password here

def get_page_content():
    """Fetch page content and return as plain text."""
    response = requests.get(URL)
    return BeautifulSoup(response.text, "html.parser").get_text()

def send_email(body, subject):
    """Send an email notification about the website status."""
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    try:
        server = smtplib.SMTP_SSL(smtp_ssl_host, smtp_ssl_port)
        server.login(username, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print(f"Email sent to {receiver}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    """Main function to check for webpage changes and send email alerts."""
    current_time = datetime.datetime.now()
    next_check_time = current_time + datetime.timedelta(hours=6)

    current_content = get_page_content()
    # print(current_content)

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            previous_content = f.read()
    else:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        previous_content = ""

    if current_content != previous_content:
        send_email(
            f"Change detected on the website: {URL}\n\nNext check scheduled at: {next_check_time.strftime('%Y-%m-%d %H:%M:%S')}", 
            "Website Change Detected!"
        )
        with open(STATE_FILE, "w") as f:
            f.write(current_content)
    else:
        send_email(
            f"No changes detected on the website: {URL}\n\nNext check scheduled at: {next_check_time.strftime('%Y-%m-%d %H:%M:%S')}", 
            "Website Status: No Changes"
        )
        with open(STATE_FILE, "w") as f:
            f.write(current_content)

if __name__ == "__main__":
    main()