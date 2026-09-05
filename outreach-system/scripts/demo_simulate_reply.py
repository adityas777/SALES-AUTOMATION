"""Demo helper: simulate an inbound reply from a business BY NAME, so a live
presentation never needs to look up an Airtable record ID first.

Runs the exact same code path as a real inbound WhatsApp/email reply would:
AI classification -> Airtable status update -> handoff queue + Slack ping
(if the label warrants it).

Usage:
    python scripts/demo_simulate_reply.py "Life Fitness 24x7" "Yes, interested! Call me."
    python scripts/demo_simulate_reply.py "Some Business" "STOP" --channel whatsapp
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.airtable_client import get_client
from src.storage.schema import BusinessFields as BF, Channel
from src.replies.reply_handler import handle_inbound_reply


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate an inbound reply for live demos")
    parser.add_argument("business_name")
    parser.add_argument("message")
    parser.add_argument("--channel", default="email", choices=["email", "whatsapp"])
    args = parser.parse_args()

    client = get_client()
    businesses = client.list_businesses()
    match = next(
        (b for b in businesses if b["fields"].get(BF.NAME, "").strip().lower() == args.business_name.strip().lower()),
        None,
    )
    if not match:
        print(f"No business found named {args.business_name!r}. Businesses on file:")
        for b in businesses[:20]:
            print(" -", b["fields"].get(BF.NAME))
        sys.exit(1)

    channel = Channel.EMAIL if args.channel == "email" else Channel.WHATSAPP
    print(f"Simulating {args.channel} reply from {match['fields'].get(BF.NAME)}:")
    print(f"  {args.message!r}")

    result = handle_inbound_reply(match["id"], channel, args.message)
    print(f"\nAI classified as: {result['label']}  (confidence {result['confidence']:.2f})")
    print("Check Airtable (Businesses status + HumanHandoffQueue) and Slack now.")


if __name__ == "__main__":
    main()
