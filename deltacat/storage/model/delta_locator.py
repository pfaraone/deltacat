from deltacat.utils.common import sha1_hexdigest
from deltacat.storage.model import partition_locator as pl
from typing import Any, Dict, Optional


def of(
        partition_locator: Optional[Dict[str, Any]],
        stream_position: Optional[int]) -> Dict[str, Any]:
    """
    Creates a partition delta locator. Stream Position, if provided, should be
    greater than that of any prior delta in the partition.
    """
    return {
        "partitionLocator": partition_locator,
        "streamPosition": stream_position,
    }


def get_partition_locator(delta_locator: Dict[str, Any]) \
        -> Optional[Dict[str, Any]]:

    return delta_locator.get("partitionLocator")


def set_partition_locator(
        delta_locator: Dict[str, Any],
        partition_locator: Optional[Dict[str, Any]]) -> None:

    delta_locator["partitionLocator"] = partition_locator


def get_stream_position(delta_locator: Dict[str, Any]) -> Optional[int]:
    return delta_locator.get("streamPosition")


def set_stream_position(
        delta_locator: Dict[str, Any],
        stream_position: Optional[int]) -> None:

    delta_locator["streamPosition"] = stream_position


def hexdigest(delta_locator: Dict[str, Any]) -> str:
    """
    Returns a hexdigest of the given Delta Locator suitable for use in
    equality (i.e. two Delta Locators are equal if they have the same
    hexdigest) and inclusion in URLs.
    """
    pl_hexdigest = pl.hexdigest(get_partition_locator(delta_locator))
    stream_position = get_stream_position(delta_locator)
    delta_locator_str = f"{pl_hexdigest}|{stream_position}"
    return sha1_hexdigest(delta_locator_str.encode("utf-8"))
