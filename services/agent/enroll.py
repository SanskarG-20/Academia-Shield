"""Exchange a short-lived student claim for a credential stored in the OS keyring."""

import json
import urllib.request
import urllib.error
from credentials import load_credential, save_credential
from config import SERVER_IP, SERVER_PORT, USE_HTTPS, REQUEST_TIMEOUT


def enroll(claim):
    protocol = "https" if USE_HTTPS else "http"
    url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/enroll"
    headers = {"Content-Type": "application/json"}
    previous = load_credential()
    if previous:
        headers["Authorization"] = f"Device {previous}"
    body = json.dumps({"claim": claim}).encode()
    def exchange(auth_headers):
        request = urllib.request.Request(url, data=body, headers=auth_headers, method="POST")
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)
    try:
        payload = exchange(headers)
    except urllib.error.HTTPError as error:
        if error.code != 401 or not previous:
            raise
        # The stored credential may already have been revoked. The claim still
        # proves the new student's identity; do not send the stale credential.
        payload = exchange({"Content-Type": "application/json"})
    credential = payload["data"]["credential"]
    save_credential(credential)
    return payload["data"]["deviceId"]
