import requests
import json
import colorama
import random

colorama.init(autoreset=True)

sso = open("sso.txt", "r").read().splitlines()
# i had multiple sso's (session cookies)


class GrokClient:
    base = "https://grok.com/rest/app-chat/conversations/new"

    def __init__(
        self,
        think: bool = False,
        deepsearch: str = "",
        systemprompt: str = "",
        disablesearch: bool = False,
    ):
        self.session = requests.Session()
        self.session.headers.update(self.get_headers())
        self.sso = random.choice(sso)
        print(
            f"{colorama.Fore.LIGHTBLACK_EX}SYS   > {colorama.Fore.RESET}Using SSO: {self.sso[:10]}...{self.sso[-10:]}"
        )
        self.cookies = self.get_cookies(self.sso)

        self.convoID = None
        self.parentID = None

        self.think = think
        self.deepsearch = deepsearch
        self.disablesearch = disablesearch
        self.systemprompt = systemprompt

    @staticmethod
    def get_headers() -> dict:
        return {
            "accept": "*/*",
            "accept-language": "en;q=0.5",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://grok.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://grok.com/",
            "sec-ch-ua": '"Not(A:Brand";v="99", "Brave";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        }

    @staticmethod
    def get_cookies(sso) -> dict:
        return {
            "x-anonuserid": "",
            "x-challenge": "",  # not needed lol?
            "x-signature": "",
            "sso": sso,
            "sso-rw": sso,
        }

    def get_payload(self, message: str = "hello") -> dict:
        data = {
            "temporary": False,
            "modelName": "grok-3",
            "message": message,
            "fileAttachments": [],
            "imageAttachments": [],
            "disableSearch": self.disablesearch,
            "enableImageGeneration": True,
            "returnImageBytes": False,
            "returnRawGrokInXaiRequest": False,
            "enableImageStreaming": True,
            "imageGenerationCount": 2,
            "forceConcise": False,
            "toolOverrides": {},
            "enableSideBySide": True,
            "isPreset": False,
            "sendFinalMetadata": True,
            "customInstructions": self.systemprompt,
            "deepsearchPreset": self.deepsearch,
            "isReasoning": self.think,
        }

        if self.convoID:
            data.update(
                {
                    "message": message,
                    "parentResponseId": self.parentID,
                }
            )

        return data

    def send_request(self, message: str = "hello") -> str:
        try:
            url = (
                self.base
                if self.convoID is None
                else f"https://grok.com/rest/app-chat/conversations/{self.convoID}/responses"
            )
            response = self.session.post(
                url, json=self.get_payload(message), cookies=self.cookies, stream=True
            )

            if response.status_code != 200:
                print(f"failed {response.status_code} {response.text}")
                return ""

            return self.parse_response(response.text)
        except requests.exceptions.RequestException as e:
            print(f"failed: {e}")
            return ""

    def parse_response(self, response_text: str) -> str:
        final_message = ""
        for line in response_text.split("\n"):
            try:
                data = json.loads(line)

                if self.convoID:
                    try:
                        resp = data.get("result", {}).get(
                            "token",
                        )
                        final_message += resp
                    except TypeError:
                        pass
                if "conversation" in data.get("result", {}):
                    self.convoID = data["result"]["conversation"]["conversationId"]
                if "response" in data.get("result", {}):
                    response = data["result"]["response"]
                    self.parentID = response["responseId"]
                    if "token" in response:
                        final_message += response["token"]
            except json.JSONDecodeError:
                continue

        return final_message


if __name__ == "__main__":
    client = GrokClient()

    try:
        while True:
            user_message = input(f"{colorama.Fore.GREEN}YOU {colorama.Fore.RESET}  > ")
            response = client.send_request(user_message)
            print(f"{colorama.Fore.GREEN}grok3 {colorama.Fore.RESET}> {response}")
    except KeyboardInterrupt:
        print(f"Bye! -> {client.convoID}")
    except Exception as e:
        print(f"err: {e}")


# tried to get a working stream, but it is not working
