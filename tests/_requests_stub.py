"""Minimal requests fallback for running unit tests before dependencies install."""

import sys
import types


def ensure_requests():
    try:
        import requests

        return requests
    except ImportError:
        module = types.ModuleType("requests")

        class RequestException(Exception):
            def __init__(self, message="", response=None):
                super().__init__(message)
                self.response = response

        class ConnectionError(RequestException):
            pass

        class Timeout(RequestException):
            pass

        class HTTPError(RequestException):
            pass

        module.exceptions = types.SimpleNamespace(
            RequestException=RequestException,
            ConnectionError=ConnectionError,
            Timeout=Timeout,
            HTTPError=HTTPError,
        )
        module.get = lambda *_args, **_kwargs: None
        module.post = lambda *_args, **_kwargs: None
        sys.modules["requests"] = module
        return module
