import pytest

from astrbot.core.utils.outbound_http import (
    PLUGIN_DOWNLOAD_URL,
    OutboundRequestError,
    pin_httpx_transport,
)


def test_pin_httpx_transport_refuses_an_unpinnable_transport():
    class Transport:
        pass

    with pytest.raises(OutboundRequestError):
        pin_httpx_transport(Transport(), PLUGIN_DOWNLOAD_URL)


def test_pin_httpx_transport_refuses_a_missing_backend():
    class Pool:
        pass

    class Transport:
        _pool = Pool()

    with pytest.raises(OutboundRequestError):
        pin_httpx_transport(Transport(), PLUGIN_DOWNLOAD_URL)
