"""Read-only Caddy adapted-JSON comparison: exact one-route-change policy.

Requires two independently generated Caddy adapted-JSON files from the
EXISTING relay's Caddy binary, against the immutable original and a
candidate with only J-Assist route inserted. No shell, AWS, network,
file modification, Caddy reload, or live traffic is performed here.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

MCP_HOST="mcp-jason.teamaot.com"
PILOT_PATH="/v1/jassist/*"
PILOT_UPSTREAM="10.87.246.157:3981"


class RelayPreflightDenied(ValueError):
    pass


def _host_match(node):
    predicates=node.get("match",[])
    return any(isinstance(m,dict)
               and m.get("host")==[MCP_HOST]
               for m in predicates if isinstance(m,dict))


def _path_match(route):
    predicates=route.get("match",[])
    return (isinstance(predicates,list) and len(predicates)==1
            and isinstance(predicates[0],dict)
            and predicates[0].get("path")==[PILOT_PATH])


def _verify_pilot_route(node):
    if not isinstance(node,dict) or not _path_match(node):
        raise RelayPreflightDenied("unexpected pilot matcher")
    stack=[node]
    upstreams=[]
    while stack:
        item=stack.pop()
        if isinstance(item,dict):
            name=item.get("handler")
            if name is not None:
                if name not in ("subroute","reverse_proxy"):
                    raise RelayPreflightDenied("pilot route contains an unreviewed handler")
                if name=="reverse_proxy":
                    hosts=item.get("upstreams",[])
                    if not isinstance(hosts,list) or len(hosts)!=1:
                        raise RelayPreflightDenied("pilot proxy must have one upstream")
                    if hosts[0] != {"dial":PILOT_UPSTREAM}:
                        raise RelayPreflightDenied("pilot upstream changed")
                    upstreams.append(hosts[0]["dial"])
            stack.extend(item.values())
        elif isinstance(item,list):
            stack.extend(item)
    if upstreams != [PILOT_UPSTREAM]:
        raise RelayPreflightDenied("pilot Caddy route missing exact proxy")


def verified_single_route_delta(baseline: dict,candidate: dict) -> bool:
    if not isinstance(baseline,dict) or not isinstance(candidate,dict):
        raise RelayPreflightDenied("adapted Caddy configurations must be objects")
    trial=copy.deepcopy(candidate)
    found=[]

    def visit(node,host_seen=False):
        if isinstance(node,dict):
            host_here=host_seen or _host_match(node)
            for field,value in list(node.items()):
                if field=="routes" and isinstance(value,list):
                    for route in list(value):
                        if isinstance(route,dict) and _path_match(route):
                            if not host_here:
                                raise RelayPreflightDenied("pilot route outside the MCP host")
                            _verify_pilot_route(route)
                            value.remove(route)
                            found.append(True)
                        else:visit(route,host_here)
                elif isinstance(value,(dict,list)):
                    visit(value,host_here)
        elif isinstance(node,list):
            for child in node:visit(child,host_seen)
    visit(trial)
    if len(found)!=1:
        raise RelayPreflightDenied("exactly one J-Assist route must be added")
    if trial!=baseline:
        raise RelayPreflightDenied(
            "candidate changes existing Caddy routes, TLS, proxy or global settings")
    return True


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-adapted",type=Path,required=True)
    parser.add_argument("--candidate-adapted",type=Path,required=True)
    args=parser.parse_args(argv)
    def read(path):
        if not path.is_file() or path.stat().st_size>2_000_000:
            raise RelayPreflightDenied("missing or oversized adapted Caddy config")
        return json.loads(path.read_text(encoding="utf-8"))
    verified_single_route_delta(
        read(args.baseline_adapted),read(args.candidate_adapted))
    print("JASSIST_RELAY_ROUTE_DELTA_VERIFIED=PASS")
    print("LIVE_CONFIG_READBACK_VERIFIED=NOT_ASSERTED")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print("JASSIST_RELAY_ROUTE_DELTA_VERIFIED=DENIED")
        print("REASON="+str(exc)[:240])
        raise SystemExit(2) from exc
