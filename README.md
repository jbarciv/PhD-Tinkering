# PhD-Tinkering
Some (useful?) resources developed during my PhD to have fun and improve my workflow. I hope this can be useful to someone!


## Content
- [My Mail Checker](#my-mail-checker)
- [Web Monitor](#web-monitor)
- [To Do](#to-do)

## My Mail Checker

This script checks your email daily for new arXiv papers, filters them by looking for a specific keywords (like "vehicle" or "motion planning" in my case), and then forwards the relevant ones to another email. It’s automated with `cron` to save 
time by only sending papers that match your keywords.

![Email Checker Workflow](/images/email_checker_before_after.png)

For more information about the mail checker, see the [my_mail_checker/README.md](my_mail_checker/README.md) file.

## Web Monitor

This script provides an automated web monitoring solution that tracks webpage changes and dispatches email alerts every 6 hours. By comparing the current webpage content with its previous state, it instantly notifies you of any detected modifications, ensuring you never miss critical updates.

> **Quick Tip:** Create a temp folder for webpage snapshots. Use a simple relative path and automate with `cron`, similar to the [my_mail_checker approach](my_mail_checker/README.md).

Dive into the implementation details in [web_monitor/web_monitor.py](web_monitor/web_monitor.py).

## To Do
- [ ] Paper titles in mail_checker are not correctly saved if they are long
- [ ] ...