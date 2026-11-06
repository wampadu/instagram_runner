"""Pinned instagrapi adapter: never automatically replay a write after a timeout."""
import random
import time
from instagrapi import Client


class NoReplayClient(Client):
    def private_request(self, endpoint, data=None, params=None, login=False,
                        with_signature=True, headers=None, extra_sig=None, domain=None):
        if not data or login:
            return super().private_request(
                endpoint, data=data, params=params, login=login,
                with_signature=with_signature, headers=headers,
                extra_sig=extra_sig, domain=domain)
        request_headers = dict(headers or {})
        if self.authorization and not any(k.lower() == "authorization" for k in request_headers):
            request_headers["Authorization"] = self.authorization
        if self.delay_range:
            time.sleep(random.uniform(*self.delay_range))
        self.private_requests_count += 1
        # The upstream wrapper retries timeouts/incomplete reads. Bypass that
        # wrapper only for writes; preserve its transport, signing and parsing.
        return self._send_private_request(
            endpoint, data=data, params=params, login=login,
            with_signature=with_signature, headers=request_headers or None,
            extra_sig=extra_sig, domain=domain)


def configure(client):
    # Apply AFTER loading saved settings, which can restore old retry values.
    client.with_challenge_flow = False
    client.read_timeout = 30
    client.delay_range = [2, 4]
    client.set_retry_config(request_timeout=1, session_retry_total=0,
                            public_request_retries_count=1)
