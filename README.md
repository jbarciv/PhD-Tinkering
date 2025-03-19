# PhD-Tinkering
Some (useful?) resources developed during my PhD to have fun and improve my workflow. I hope this can be useful to someone!


## Content
- [PhD-Tinkering](#phd-tinkering)
  - [Content](#content)
  - [My Mail Checker](#my-mail-checker)

## My Mail Checker

This script checks your email daily for new arXiv papers, filters them by looking for a specific word (like "vehicle" in my case), and then forwards the relevant ones to another email. It’s automated with `cron` to save time by only sending papers that match your keywords.

For more information about the mail checker, see the [my_mail_checker/README.md](my_mail_checker/README.md) file.

## Web Monitor

This script provides an automated web monitoring solution that tracks webpage changes and dispatches email alerts every 6 hours. By comparing the current webpage content with its previous state, it instantly notifies you of any detected modifications, ensuring you never miss critical updates.

![Email Checker Workflow](/images/email_checker_before_after.png)

> **Tip:** Create a dedicated temporary folder for storing webpage snapshots. Specify a relative path in the script to enable seamless state comparison.

Dive into the implementation details in [web_monitor/web_monitor.py](web_monitor/web_monitor.py).