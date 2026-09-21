from __future__ import annotations

from typing import Any, Mapping

from connectors.kyocera_kfs.client import KyoceraKfsSessionClient

SEARCH_FIELDS = {
    "serial_number": "serialNumber",
    "asset_number": "assetNumber",
    "equipment_id": "equipmentId",
    "hostname": "hostname",
    "ip_address": "ipAddress",
    "model_name": "modelName",
    "customer_name": "customerName",
    "location": "location",
}

SEARCH_TEXT_FIELDS = tuple(SEARCH_FIELDS.values())

SUPPLY_ATTRIBUTES = (
    "manufacturer",
    "modelName",
    "serialNumber",
    "managementStatus",
    "blackOEMPartNumber",
    "cyanOEMPartNumber",
    "magentaOEMPartNumber",
    "yellowOEMPartNumber",
    "blackTonerLevel",
    "cyanTonerLevel",
    "magentaTonerLevel",
    "yellowTonerLevel",
    "wasteTonerStatus",
    "tonerReplacementPrediction",
    "replacementTimeTonerLevels",
    "maintenanceKit",
)


def common(
    client: KyoceraKfsSessionClient,
    bodid: str,
    additions: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "RequestFrom": client.credentials["request_from"],
        "RequestTo": client.credentials["request_to"],
        "BODID": bodid,
        **dict(additions),
    }


def root_group_ids(client: KyoceraKfsSessionClient) -> list[str]:
    payload = client.call(
        "/KFS/GroupList",
        common(
            client,
            "Global_KFS_Pull_GroupList",
            {"groupAttrIds": ["all"]},
        ),
    )
    tree = payload.get("grpTree")
    if isinstance(tree, Mapping):
        roots = [
            str(item).strip()
            for item in tree.get("topGroups") or []
            if str(item).strip()
        ]
        if roots:
            return roots
    return [
        str(group.get("groupId")).strip()
        for group in payload.get("groups") or []
        if isinstance(group, Mapping)
        and str(group.get("groupId") or "").strip()
    ]


def require_device_id(arguments: Mapping[str, Any]) -> str:
    device_id = str(
        arguments.get("device_id")
        or arguments.get("resource_id")
        or ""
    ).strip()
    if not device_id:
        raise ValueError("device_id or resource_id is required")
    return device_id


def device_get(
    client: KyoceraKfsSessionClient,
    device_id: str,
    attributes: tuple[str, ...],
    counters: tuple[str, ...],
) -> Mapping[str, Any]:
    return client.call(
        "/KFS/Device",
        common(
            client,
            "Global_KFS_Pull_Device",
            {
                "device": device_id,
                "deviceAttrIds": list(attributes),
                "counters": list(counters),
            },
        ),
    )


def device_search(
    client: KyoceraKfsSessionClient,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    group_id = str(arguments.get("group_id") or "").strip()
    roots = [group_id] if group_id else root_group_ids(client)

    devices: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        payload = client.call(
            "/KFS/DeviceList",
            common(
                client,
                "Global_KFS_Pull_DeviceList",
                {
                    "groupId": root,
                    "scope": 1,
                    "deviceAttrIds": ["all"],
                    "counters": ["total"],
                },
            ),
        )
        for device in payload.get("devices") or []:
            if not isinstance(device, Mapping):
                continue
            device_id = str(device.get("deviceId") or "").strip()
            if device_id and device_id in seen:
                continue
            if device_id:
                seen.add(device_id)
            devices.append(dict(device))

    matched = [device for device in devices if matches(device, arguments)]
    limit = max(1, min(int(arguments.get("limit") or 100), 1000))
    return {
        "devices": matched[:limit],
        "matched_count": len(matched),
        "searched_count": len(devices),
        "status": {
            "code": 200,
            "messageResource": "string-serverres-success",
        },
    }


def matches(
    device: Mapping[str, Any],
    arguments: Mapping[str, Any],
) -> bool:
    attrs = device.get("attributes")
    attributes = attrs if isinstance(attrs, Mapping) else {}

    for argument_name, attribute_name in SEARCH_FIELDS.items():
        expected = str(arguments.get(argument_name) or "").strip()
        if not expected:
            continue
        actual = str(attributes.get(attribute_name) or "").strip()
        if actual.casefold() != expected.casefold():
            return False

    query = str(arguments.get("search") or "").strip().casefold()
    if not query:
        return True
    haystack = [
        str(device.get("deviceId") or ""),
        *[str(attributes.get(name) or "") for name in SEARCH_TEXT_FIELDS],
    ]
    return any(query in value.casefold() for value in haystack)


def alerts_list(
    client: KyoceraKfsSessionClient,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    detail = str(arguments.get("detail") or "string-errorcode_all")
    base: dict[str, Any] = {"detail": detail}
    if arguments.get("from_acquisition_date") is not None:
        base["fromAcquisitionDate"] = int(arguments["from_acquisition_date"])

    device_id = str(arguments.get("device_id") or "").strip()
    if device_id:
        body = dict(base)
        body["device"] = device_id
        return client.call(
            "/KFS/DeviceLog",
            common(client, "Global_KFS_Pull_DeviceLog", body),
        )

    group_id = str(arguments.get("group_id") or "").strip()
    roots = [group_id] if group_id else root_group_ids(client)
    devices: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        body = dict(base)
        body.update(
            {
                "groupId": root,
                "groupTreeState": int(arguments.get("group_tree_state") or 3),
            }
        )
        payload = client.call(
            "/KFS/DeviceLogList",
            common(client, "Global_KFS_Pull_DeviceLogList", body),
        )
        for device in payload.get("devices") or []:
            if not isinstance(device, Mapping):
                continue
            key = str(device.get("deviceId") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            devices.append(dict(device))
    return {
        "devices": devices,
        "status": {
            "code": 200,
            "messageResource": "string-serverres-success",
        },
    }
