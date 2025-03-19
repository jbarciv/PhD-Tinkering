#!/usr/bin/env python

import time
import email
import imaplib
import smtplib
import re
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

def log(message):
    """ Print log message with timestamp """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

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
    """ Send an email with improved HTML formatting """
    start_time = time.time()
    msg = MIMEText(body, "html")  # Use HTML format for better styling
    msg['Subject'] = "Your Daily ArXiv Articles... Master"
    msg['From'] = sender
    msg['To'] = receiver

    try:
        server = smtplib.SMTP_SSL(smtp_ssl_host, smtp_ssl_port)
        server.login(username, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()

        elapsed_time = time.time() - start_time
        log(f"Email sent to {receiver} | Time taken: {elapsed_time:.2f}s")
    except Exception as e:
        log(f"Failed to send email: {e}")

def prioritize_articles(articles):
    """ Sort and categorize articles based on priority criteria """
    categories = {
        "ODD-related": [],
        "Motion Planning & Trajectory Generation": [],
        "Reinforcement Learning": [],
        "Control Systems": [],
        "Other Vehicle Articles": [],
    }

    filtered_articles = []

    # First, remove articles containing UAV, drone, quadrotor, or underwater
    for article in articles:
        lower_article = article.lower()
        if any(term in lower_article for term in ["uav", "drone", "quadrotor", "underwater"]):
            continue  # Skip these articles
        filtered_articles.append(article)

    # Now categorize the remaining articles
    for article in filtered_articles:
        upper_article = article.upper()
        lower_article = article.lower()

        if "ODD" in upper_article:
            categories["ODD-related"].append(article)
        
        elif "vehicle" in lower_article:
            has_motion = "motion planning" in lower_article or "trajectory generator" in lower_article
            has_rl = "reinforcement learning" in lower_article

            if has_motion and not has_rl:
                categories["Motion Planning & Trajectory Generation"].append(article)
            elif has_rl:
                categories["Reinforcement Learning"].append(article)
            else:
                categories["Other Vehicle Articles"].append(article)


    return categories

def process_unread_emails():
    server = imaplib.IMAP4_SSL(imap_ssl_host, imap_ssl_port)
    server.login(username, password)
    server.select('INBOX')

    log("Checking for unread emails in inbox...")
    result, data = server.search(None, 'UNSEEN')
    unread_uids = [int(s) for s in data[0].split()]
    log(f"Unread emails found: {len(unread_uids)}")

    articles = []

    for uid in unread_uids:
        start_time = time.time()
        result, data = server.fetch(str(uid), '(RFC822)')
        msg = email.message_from_bytes(data[0][1])
        text = get_first_text_block(msg)

        # Extract articles
        lines = text.split("\n")
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

        elapsed_time = time.time() - start_time
        log(f"Processed mail | Time taken: {elapsed_time:.2f}s")

    server.logout()

    # Prioritize and categorize articles
    categorized_articles = prioritize_articles(articles)

    # Format categorized articles using HTML
    email_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            h3 {{ color: #007BFF; }}
            hr {{ border: 1px solid #ddd; }}
            .article {{ margin-bottom: 20px; }}
        </style>
    </head>
    <body>
    <h3>Master, I have found {sum(len(v) for v in categorized_articles.values())} articles for you today.</h3>
    """

    for category, article_list in categorized_articles.items():
        if article_list:
            email_body += f"<h3>📜 {category.upper()} 📜</h3><hr>"

            for article in article_list:
                lines = [line.strip() for line in article.split("\r\n") if line.strip()]
                arxiv_id = title = categories = link = abstract = date = comments = ""
                authors = []
                
                in_abstract = False
                in_authors = False

                for i, line in enumerate(lines):
                    if line.startswith("arXiv:"):
                        arxiv_id = line.split()[0]

                    elif line.startswith("Title:"):
                        title = line.replace("Title:", "").strip()

                    elif line.startswith("Authors:"):
                        in_authors = True
                        authors.append(line.replace("Authors:", "").strip())

                    elif in_authors and not line.startswith("Categories:"):
                        authors.append(line.strip())  # Multi-line authors handling

                    elif line.startswith("Categories:"):
                        in_authors = False
                        categories = line.replace("Categories:", "").strip()
                    
                    elif line.startswith("Date:"):
                        date = re.sub(r" \(.*\)", "", line.replace("Date:", "").strip())

                    elif line.startswith("Comments:"):
                        comments = line.replace("Comments:", "").strip()

                    elif line.startswith("\\\\") and in_abstract == False:
                        in_abstract = True
                        continue  # Skip this line
                    
                    elif line.startswith("\\\\") and in_abstract == True:
                        in_abstract = False
                        match = re.search(r"https://arxiv.org/abs/\d+\.\d+", line)
                        if match:
                            link = match.group(0)
                        continue  # Do not add this line to the abstract
                    
                    if in_abstract:
                        if "------------------------------------------------------------------------------" in line or "\\ (" in line:
                            in_abstract = False  # Stop abstract before unwanted text
                            continue
                        abstract += line + " "

                # Add article info to email body
                email_body += f"""
                <div class="article">
                    <b>{title}</b><br>
                    <i>📅 Date: {date}</i><br>
                    <i>✍️ Authors: {" ".join(authors)}</i><br>
                    {f'💬 Comments: {comments}<br>' if comments else ''}
                    📝 <b>Abstract:</b> {abstract.strip()}<br>
                    🔗 <a href="{link}" target="_blank">Read more</a><br>
                </div>
                <hr>
                """

    email_body += """
    <br><br>
    <p>Your humble assistant,<br>🤖 <b>ArxivBot</b></p>
    </body></html>
    """

    if any(categorized_articles.values()):
        send_email(email_body)
    else:
        log("No relevant articles found.")

# Run the email processing
process_unread_emails()