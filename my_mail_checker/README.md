# My Mail Checker

Two Ph.D. students talk...
> **Huerts (an experienced Ph.D. student):**  
> Hey, have you subscribed to the arXiv newsletter yet? It’s a goldmine of cutting-edge research.
> 
> **Me (a nooby Ph.D. student):**  
> Oh, that sounds useful! I’ll subscribe right now!
> 
> **[The next day]**
> 
> **Me:**  
> Huerts… I think I made a mistake.
> 
> **Huerts:**  
> What happened?
> 
> **Me:**  
> My inbox is under attack. The arXiv emails… they come every single day. And they’re LONG. Like, “bring a lunch and a blanket” long.
> 
> **Huerts:**  
> (*laughs*) Welcome to academia, my friend. It’s the price of knowledge!
> 
> **Me:**  
> Nope, I refuse. I’m a robotics student—I’ll automate this. I’m gonna write some code to filter out useless papers...
> 
> **Huerts:**  
> You subscribed for knowledge and now you’re using code to delete it? Beautiful irony.
> 
> **Me:**  
> Work smarter, not harder.

## What?

I'm trying to filter out papers that aren't related to my research area. I asked ChatGPT for help with the code using some reference examples, and after a few iterations, this is what I’ve got.

I have tried to make a good filtering removing unwanted papers (i.e., those that talk about drones, UAVs, underwater vehicles, etc.). Also, HTML has been added to improve readibility.

I’m not a fan of using code I haven’t fully developed or understood, but this works, and I needed it up and running quickly. Feel free to submit any PRs with improvements.

Cheers!

## Steps

1) Subscribe to *arxiv* newsletters. Follow [this](https://info.arxiv.org/help/subscribe.html).
2) Create a mail app password. In *gmail* this can be done [here](https://myaccount.google.com/apppasswords).
   - You will end with something like this: `abcd efgh ijkl mnio`
3) Download the `my_mail_checker.py` file and place it in a hidden location in your personal laptop or server. 
4) Change the password, username, sender, and receiver accordingly.
    > **Warning!**\
    > *I understand this is not the most secure approach, but **in my case, the email is only used for this purpose**. It’s essentially no different from receiving emails from sources like arXiv, which don’t contain sensitive data.*
1) Make it executable: `chmod +x my_mail_checker.py`
2) Define a `crontab` execution.
    1) First open the crontab file:
        ```
        crontab -e
        ```
    2) Add this line (more info [here](https://man7.org/linux/man-pages/man5/crontab.5.html)):
        ```
        0 9 * * * /usr/bin/python3 /home/yourUser/thePathToYourFile/.my_mail_checker/unread_inbox_checker.py
        ```
3) Enjoy!

## Acknowledgments

Special thanks to [@javierckr](https://github.com/javierckr) for all his advice and support. He is the ultimate tinker boss! 🔥

## References

- [Use Python to send and receive emails](https://gist.github.com/nickoala/569a9d191d088d82a5ef5c03c0690a02)
- [imaplib — IMAP4 protocol client](https://docs.python.org/3/library/imaplib.html)
- [smtplib — SMTP protocol client](https://docs.python.org/3/library/smtplib.html)
