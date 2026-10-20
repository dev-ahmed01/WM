"""Opt-in outbound reconciliation runner.

Set WORKMATE_OUTBOUND_ENABLED=true only after provisioning approved HTTPS
targets and network egress controls. Run once from an external job scheduler;
the process never runs in a web request or on module import.
"""
from __future__ import annotations

import argparse
import json
from app.services.work_integration_outbound import dispatch_batch

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true",required=True)
    parser.add_argument("--limit",type=int,default=10,choices=range(1,26),metavar="{1..25}")
    args=parser.parse_args()
    result=dispatch_batch(args.limit)
    # Only aggregate metadata; never include URLs, bearer keys or payloads.
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
