"""A model call that failed on the way: one rule, used by the agent team and by the worksheet.

A call is made once more, and only once, when its reply never came (the connection dropped or timed out, or the
provider answered with a server error) or when the provider is limiting the key (HTTP 429). A reply that came,
however bad, is never asked again, and neither is a refusal such as a bad key or an empty credit balance.

Until 2026-11-22 the team and the worksheet each had a copy of this rule and the copies disagreed. Neither
tried a rate limit again. The team's copy read only `status_code`, so it missed Google's errors, which carry
`code`: a "model is overloaded" answer ended a run. And a call that stalled had no time limit at all on an
Anthropic or a Google model, so a run could hang for good. This file imports no provider's SDK: it reads
names and status numbers.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

CONNECTION_ERRORS = {"APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout", "ReadError", "ReadTimeout",
                     "WriteError", "WriteTimeout", "PoolTimeout", "Timeout", "RemoteProtocolError", "ProtocolError",
                     "ChunkedEncodingError", "ConnectionError", "InternalServerError", "ServiceUnavailableError",
                     "OverloadedError", "ServerError"}
RATE_LIMIT_ERRORS = {"RateLimitError"}
SERVER_STATUS = (408, 500, 502, 503, 504, 529)
RATE_LIMIT_STATUS = 429
RETRY_WAIT_SECONDS = 30        # before a call whose reply never came is made once more
RATE_LIMIT_WAIT_SECONDS = 60   # before a call the provider limited is made once more
REQUEST_TIME_LIMIT_SECONDS = 600   # one HTTP request to the provider, where its client takes a limit
CALL_TIME_LIMIT_SECONDS = 1200     # one whole role call (a role reads its files in several requests)


def status_of(error: BaseException) -> int | None:
    """The HTTP status an error carries. Anthropic and OpenAI name it status_code, Google names it code, and
    requests keeps it on the response."""
    for value in (getattr(error, "status_code", None), getattr(error, "code", None),
                  getattr(getattr(error, "response", None), "status_code", None)):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def retry_reason(error: BaseException | None) -> str | None:
    """"rate limit" or "dropped" when the same call may be made once more, read through the whole chain of
    causes; None when the call must not be repeated."""
    seen: set[int] = set()
    reason = None
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        status, name = status_of(error), type(error).__name__
        if status == RATE_LIMIT_STATUS or name in RATE_LIMIT_ERRORS:
            return "rate limit"
        if isinstance(error, (ConnectionError, TimeoutError)) or name in CONNECTION_ERRORS or status in SERVER_STATUS:
            reason = "dropped"
        error = error.__cause__ or error.__context__
    return reason


def dropped_connection(error: BaseException | None) -> bool:
    """True when a model call failed on the way and may be made once more."""
    return retry_reason(error) is not None


def within_time_limit(call: Callable[[], Any], seconds: float, what: str) -> Any:
    """call(), or TimeoutError when it has not returned in time.

    The call runs in a helper thread, because the Google client takes no time limit and a stalled request never
    returns. The thread is a daemon: a call that never returns cannot keep the program alive, and its late
    answer is thrown away.
    """
    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["value"] = call()
        except BaseException as error:  # handed to the caller's thread below
            box["error"] = error

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"{what}: the model did not answer in {int(seconds // 60)} minutes")
    if "error" in box:
        raise box["error"]
    return box["value"]
