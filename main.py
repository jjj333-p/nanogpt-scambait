"""
This code is provided on an as-is warranty-free basis by Joseph Winkie <jjj333.p.1325@gmail.com>

This is the main code that interacts with the LLM and the email, and generates the new system prompt to test

This code is licensed under the A-GPL 3.0 license found both in the "LICENSE" file of the root of this repository
as well as https://www.gnu.org/licenses/agpl-3.0.en.html. Read it to know your rights.

A complete copy of this codebase as well as runtime instructions can be found at
https://github.com/jjj333-p/llama-scambait/
"""
import asyncio
import imaplib
import json
import os
import random
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from time import sleep, time

# from ollama import chat
# from ollama import ChatResponse
import mailparser
import requests

from xmpp_bot import create_bot

if __name__ != "__main__":
    raise ImportError("This script should only be run directly and not imported.")

# directory to store message history
if not os.path.exists('./db/'):
    os.mkdir('./db/')

# Email details
with open("login.json", "r") as file:
    login = json.load(file)

# nanogpt headers
headers = {
    "Authorization": f"Bearer {login['api_key']}",
    "Content-Type": "application/json",
}


# replacement for the ollama library, return string instead of object
def chat(messages: list[dict[str, str]]) -> tuple[str, dict]:
    data = {
        "model": login["model"],
        "messages": messages,
        "stream": False  # Disable streaming
    }

    response = requests.post(
        "https://nano-gpt.com/api/v1/chat/completions",
        headers=headers,
        json=data,
        stream=False  # Disable streaming in requests
    ).json()

    # hopefully error free parsing
    resp_choices = response.get('choices', [])
    if len(resp_choices) < 1:
        return "", response
    choice = resp_choices[0]
    llm_message = choice.get('message')
    if not llm_message:
        return "", response
    llm_content = llm_message.get('content', '')
    return llm_content, response


xmpp_conf = login.get("xmpp_conf")
if xmpp_conf:
    xmpp, xmpp_future = create_bot(xmpp_conf)


async def main():
    run: int = 0

    while True:
        print("starting run", run)
        run += 1

        start_time = time()

        try:
            # Connect to the server
            mail = imaplib.IMAP4_SSL(login["imap_addr"], login["imap_port"])
            mail.login(login["email"].split("@")[0], login["password"])

            for box in ["INBOX", "Junk"]:

                # Select the mailbox you want to use
                mail.select(box)

                # Search for new emails
                _status, messages = mail.search(None, "UNSEEN")
                email_ids = messages[0].split()

                # fetch email ids we just searched for
                for num in email_ids:
                    typ, data = mail.fetch(num, '(RFC822)')

                    # no idea why a message id returns a list but okay
                    for response in data:

                        # everything does this, i have no idea
                        if not isinstance(response, tuple):
                            continue

                        msg = mailparser.parse_from_bytes(response[1])

                        # sanity checks
                        if len(msg.from_) < 1 or len(msg.from_[0]) < 2:
                            continue

                        # parse in details
                        sender_name, sender, *_ = msg.from_[0]

                        # this can only be internal messages
                        if sender is None or len(sender) < 5:
                            continue

                        if msg.reply_to and len(msg.reply_to) > 0:
                            reply_to = msg.reply_to[0]
                            if len(reply_to[1]) > 0:
                                sender_name, sender, *_ = reply_to

                        subject: str = msg.subject if msg.subject else "No subject"
                        body_lines: list[str] = []

                        # rid of the replies, rely on stored content for that
                        for line in msg.text_plain[0].splitlines():
                            if login["email"].split("@")[0] in line or login["displayname"] in line or line.startswith(
                                    "> "):
                                break
                            else:
                                body_lines.append(line)

                        body: str = "\r\n".join(body_lines)

                        print("From:", sender)
                        print("Subject:", subject)
                        print("Body:", body)

                        subject_by_words: list[str] = subject.split()

                        print(xmpp_conf)
                        if xmpp_conf:
                            xmpp_body = f"`{" ".join(subject_by_words)}` sent by `{sender_name} <{sender}>`\n{'\n> '.join(body_lines)}"
                            try:
                                print(xmpp_body)
                                xmpp.send_message(
                                    mto=xmpp_conf["user"],
                                    mbody=xmpp_body,
                                    mtype="chat",
                                )
                            except Exception as e:
                                print("Error sending XMPP message:", e)

                        # sanatize email addr to save by
                        if subject_by_words[0] == "Re:" or subject_by_words[0] == "re:" or subject_by_words[0] == "RE:":
                            del subject_by_words[0]
                        encoded: str = re.sub(r"^[ .]|[/<>:\"\\|?*]+|[ .]$", "_", sender)

                        # read in history from disk, or emplace default
                        if os.path.exists(f'./db/{encoded}.json'):
                            with open(f'./db/{encoded}.json', 'r') as file:
                                j = json.load(file)
                                history_load = j["history"]
                                use_edited_sysprompt = j["use_edited_sysprompt"]
                        else:
                            history_load = []
                            # true or false random choice
                            use_edited_sysprompt = bool(random.randint(0, 1))

                        sysprompt = f'{login["default_prompt"]}\nThe subject is "{" ".join(subject_by_words)}" sent by {sender_name} <{sender}>'

                        history = [
                                      {
                                          "role": "system",
                                          "content": sysprompt,
                                          "tuned": True,
                                      }
                                  ] + history_load + [
                                      {
                                          "role": "user",
                                          "content": body,
                                          "tuned": False,
                                      }
                                  ]

                        # compute response
                        response_body: str = ""
                        err_str: str = ""
                        try:
                            response_body, response_obj = chat(messages=history)
                        except Exception as e:
                            err_str: str = str(e)

                        if response_body != "":
                            if xmpp_conf:
                                xmpp_body = f"*Response to* `{" ".join(subject_by_words)}` sent by `{sender_name} <{sender}>`\n{'\n> '.join(response_body.splitlines())}"
                                try:
                                    xmpp.send_message(
                                        mto=xmpp_conf["user"],
                                        mbody=xmpp_body,
                                        mtype="chat",
                                    )
                                except Exception as e:
                                    print("Error sending XMPP message:", e)
                        elif xmpp_conf:
                            if err_str != "":
                                err_str = str(response_obj)
                            xmpp_body = f"Error getting response from LLM\n{'\n> '.join(err_str.splitlines())}"
                            try:
                                xmpp.send_message(
                                    mto=xmpp_conf["user"],
                                    mbody=xmpp_body,
                                    mtype="chat",
                                )
                            except Exception as e:
                                print("Error sending XMPP message:", e)
                            break
                        else:
                            break

                        # create email object
                        response_message = MIMEMultipart()
                        response_message["From"] = formataddr((login["displayname"], login["email"]))
                        response_message["To"] = sender
                        if subject.startswith("Re:"):
                            response_message["Subject"] = subject
                        else:
                            response_message["Subject"] = f"Re:{subject}"
                        response_message.attach(MIMEText(response_body, "plain"))

                        # send email
                        try:
                            with smtplib.SMTP_SSL(login["smtp_addr"], login["smtp_port"]) as server:
                                server.login(login["email"].split('@')[0], login["password"])
                                server.send_message(response_message)
                            print("Email sent successfully!")
                        except Exception as e:
                            print(f"Error: {e}")
                            break

                        # we dont want system prompt to be saved
                        del history[0]

                        history.append({
                            "role": "assistant",
                            "content": response_body,
                            "system_prompt": sysprompt,
                        })

                        with open(f'./db/{encoded}.json', 'w', encoding="utf-8") as file:
                            j = {
                                "use_edited_sysprompt": use_edited_sysprompt,
                                "history": history,
                            }
                            json.dump(j, file, indent=4)

            mail.logout()
        except Exception as e:
            print(f"Error: {e}")

        # stop from raping my poor vps
        # stalwart is light, but it needs all the help it can get
        dur = time() - start_time
        print(f'done run {run - 1} in {dur} seconds')
        if dur < 30:
            sleep(30 - dur)


loop = asyncio.get_event_loop()
try:
    if xmpp_conf:
        loop.run_until_complete(xmpp_future)
    loop.create_task(main())
    loop.run_forever()
except KeyboardInterrupt:
    if xmpp_conf:
        xmpp.disconnect()
    loop.stop()
finally:
    loop.close()
