import json
from .core import ModelRouter, run_chain

RESPONSE_BANK = {
    ("quarterly-status", "extract", "cascade-lite"): [
        json.dumps(["Project Atlas is 3 weeks behind the Q3 schedule",
                    "The mobile client team is down two engineers",
                    "A pending auth-service security patch is unreviewed"]),
    ],
    ("quarterly-status", "analyze", "cascade-reason"): [
        json.dumps([{"risk": "Schedule slip on Project Atlas", "severity": "MEDIUM"},
                    {"risk": "Pending security patch leaves a known vulnerability open", "severity": "HIGH"}]),
    ],
    ("quarterly-status", "format", "cascade-lite"): [
        "EXECUTIVE SUMMARY: Project Atlas is behind schedule and a security patch remains "
        "pending review, which should be prioritized this week ahead of other open items.",
    ],
    ("payment-outage", "extract", "cascade-lite"): [
        json.dumps(["Checkout API returned elevated 5xx errors for 40 minutes",
                    "Root cause was a bad config pushed during a routine deploy"]),
    ],
    ("payment-outage", "analyze", "cascade-reason"): [
        '{not valid json at all',             # attempt 1: malformed
        '{also not valid json!!',             # attempt 2: malformed again
    ],
    ("payment-outage", "analyze", "cascade-reason-alt"): [
        json.dumps([]),                        # fallback: valid JSON, but an empty list -- fails content validation
    ],
}


def main():
    router = ModelRouter(RESPONSE_BANK)
    for doc in ["quarterly-status", "payment-outage"]:
        print(f"\n=== {doc} ===")
        result = run_chain(router, doc)
        print("\n".join(result.log))
        if result.aborted:
            print(f"CHAIN ABORTED: {result.error}")
            print(f"(facts retained for debugging: {len(result.facts) if result.facts else 0})")
        else:
            print(f"Facts: {result.facts}")
            print(f"Risks: {result.risks}")
            print(f"Report: {result.report}")


if __name__ == "__main__":
    main()
