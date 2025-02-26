#!/usr/bin/env python

import time
import email
import imaplib
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

# IMAP Settings
imap_ssl_host = 'imap.gmail.com'
imap_ssl_port = 993
username = 'mailToCheck@gmail.com'
password = 'yourAppEmailPassword'

# SMTP Settings
smtp_ssl_host = 'smtp.gmail.com'
smtp_ssl_port = 465
sender = 'senderEmail@gmail.com'
receiver = 'receiverEmail@gmail.com'

# Search criteria
criteria = {
    'FROM': 'cs@arxiv.org.com',
    'SUBJECT': 'cs daily Subj-class mailing',
}
uid_max = 0

def log(message):
    """ Print log message with timestamp """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def search_string(uid_max, criteria):
    """ Generate IMAP search query """
    c = list(map(lambda t: (t[0], '"'+str(t[1])+'"'), criteria.items())) + [('UID', '%d:*' % (uid_max+1))]
    return '(%s)' % ' '.join(sum(c, ()))

def get_first_text_block(msg):
    """ Extract the first text block from an email """
    type_ = msg.get_content_maintype()
    if type_ == 'multipart':
        for part in msg.get_payload():
            if part.get_content_maintype() == 'text':
                return part.get_payload()
    elif type_ == 'text':
        return msg.get_payload()
    return ""

def send_email(body):
    """ Send an email with a fixed subject and the given body """
    start_time = time.time()
    msg = MIMEText(body)
    msg['Subject'] = "Your Daily Arxive Articles... Master"
    msg['From'] = sender
    msg['To'] = receiver

    try:
        # Ensure a new connection to SMTP
        server = smtplib.SMTP_SSL(smtp_ssl_host, smtp_ssl_port)
        server.login(username, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()

        elapsed_time = time.time() - start_time
        log(f"Email sent to {receiver} | Time taken: {elapsed_time:.2f}s")
    except Exception as e:
        log(f"Failed to send email: {e}")

def process_unread_emails():
    global uid_max
    server = imaplib.IMAP4_SSL(imap_ssl_host, imap_ssl_port)
    server.login(username, password)
    server.select('INBOX')

    log("Checking for unread emails in inbox...")
    result, data = server.search(None, 'UNSEEN')
    unread_uids = [int(s) for s in data[0].split()]
    log(f"Unread emails found: {len(unread_uids)}")

    # Process all unread emails first
    for uid in unread_uids:
        start_time = time.time()  # Define start_time here
        result, data = server.fetch(str(uid), '(RFC822)')
        msg = email.message_from_bytes(data[0][1])
        text = get_first_text_block(msg)
        mail_subject = msg["Subject"] or "(No Subject)"
        mail_time = msg["Date"] or "(Unknown Time)"
        log(f"Processing unread email | Time: {mail_time} | Subject: {mail_subject}")

        # Extract articles
        lines = text.split("\n")
        articles = []
        article = []
        
        for line in lines:
            if line.startswith("arXiv:"):
                if article:
                    articles.append("\n".join(article))
                article = [line]  # Start new article
            else:
                article.append(line)
        if article:
            articles.append("\n".join(article))  # Last article
        
        # Filter articles that contain "vehicle"
        relevant_articles = []
        for article in articles:
            if "vehicle" in article.lower():
                relevant_articles.append(article.strip())
        
        # If relevant articles found, send one email with all of them
        if relevant_articles:
            intro = f"Master, I have found {len(relevant_articles)} articles for you today.\n\n"
            separator = "\n--------------------------------------------------"
            email_body = intro + separator.join(relevant_articles) + "\n\nYour humble assistant,\nArxivBot 🤖"
            send_email(email_body)
        else:
            log("No relevant articles found in this email.")

        elapsed_time = time.time() - start_time
        log(f"Processed mail | Time taken: {elapsed_time:.2f}s")

    server.logout()



def process_new_emails():
    global uid_max
    log("Checking for new emails...")
    server = imaplib.IMAP4_SSL(imap_ssl_host, imap_ssl_port)
    server.login(username, password)
    server.select('INBOX')
    
    result, data = server.uid('search', None, search_string(uid_max, criteria))
    uids = [int(s) for s in data[0].split()]
    new_mails = 0
    
    for uid in uids:
        if uid > uid_max:
            start_time = time.time()
            result, data = server.uid('fetch', str(uid), '(RFC822)')
            msg = email.message_from_bytes(data[0][1])
            uid_max = uid  # Update uid_max after processing email
            text = get_first_text_block(msg)
            mail_subject = msg["Subject"] or "(No Subject)"
            mail_time = msg["Date"] or "(Unknown Time)"
            log(f"New mail received | Time: {mail_time} | Subject: {mail_subject}")
            new_mails += 1
            
            # Extract articles
            lines = text.split("\n")
            articles = []
            article = []
            
            for line in lines:
                if line.startswith("arXiv:"):
                    if article:
                        articles.append("\n".join(article))
                    article = [line]  # Start new article
                else:
                    article.append(line)
            if article:
                articles.append("\n".join(article))  # Last article
            
            # Filter articles that contain "vehicle"
            relevant_articles = []
            for article in articles:
                if "vehicle" in article.lower():
                    relevant_articles.append(article.strip())
            
            # If relevant articles found, send one email with all of them
            if relevant_articles:
                intro = f"Master, I have found {len(relevant_articles)} articles for you today.\n\n"
                separator = "\n--------------------------------------------------"
                email_body = intro + separator.join(relevant_articles) + "\n\nYour humble assistant,\nArxivBot 🤖"
                send_email(email_body)
            else:
                log("No relevant articles found in this email.")
            
            elapsed_time = time.time() - start_time
            log(f"Processed mail | Time taken: {elapsed_time:.2f}s")
    
    if new_mails == 0:
        log("No new relevant emails found.")
    
    server.logout()


# First process all unread emails, then start the loop for new ones
process_unread_emails()

# Start monitoring loop for new emails
# while True:
#     process_new_emails()
#     time.sleep(30)  # Check for new emails every 30 seconds
