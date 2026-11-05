"""Command-line entry point: python -m larkspur <command>."""

import argparse
import os
import sys
import urllib.error

from . import db
from .agent import CUSTOMER_ID, TRIAGE_TASK, customer_agent, triage_agent
from .grader import CHALLENGES, check
from .model import OpenAICompatibleModel


def _print_tool(name, args, result):
    print(f"  [tool] {name}({args}) -> {result}")


def _connect():
    conn = db.connect(os.environ.get("LARKSPUR_DB", "larkspur.db"))
    if conn.execute("SELECT name FROM sqlite_master WHERE name = 'orders'").fetchone() is None:
        db.reset(conn)
    return conn


def cmd_reset(args):
    db.reset(_connect())
    print("Lab data reset.")


def cmd_chat(args):
    agent = customer_agent(_connect(), OpenAICompatibleModel.from_env(), args.fixed, _print_tool)
    print(f"Chatting with Larkspur support as customer '{CUSTOMER_ID}'. Type 'exit' to quit.")
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            break
        if text in ("exit", "quit"):
            break
        if text:
            print(f"agent> {agent.send(text)}")


def cmd_ticket(args):
    ticket_id = db.submit_ticket(_connect(), CUSTOMER_ID, args.subject, args.body)
    print(f"Ticket {ticket_id} submitted as '{CUSTOMER_ID}'.")


def cmd_triage(args):
    agent = triage_agent(_connect(), OpenAICompatibleModel.from_env(), args.fixed, _print_tool)
    print("Running the internal triage agent over open tickets...")
    print(f"agent> {agent.send(TRIAGE_TASK)}")


def cmd_check(args):
    results = check(_connect())
    for cid, description in CHALLENGES.items():
        print(f"{cid} [{'SOLVED' if results[cid] else 'open'}] {description}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="larkspur", description="Larkspur Outfitters agent lab")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reset", help="reset lab data").set_defaults(func=cmd_reset)
    for name, func, text in (
        ("chat", cmd_chat, "chat with the customer support agent"),
        ("triage", cmd_triage, "run the internal ticket triage agent"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("--fixed", action="store_true", help="use the fixed tools")
        p.set_defaults(func=func)
    p = sub.add_parser("ticket", help="submit a support ticket as the customer")
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.set_defaults(func=cmd_ticket)
    sub.add_parser("check", help="show challenge progress").set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach the model endpoint ({exc}). See README: Setup.")
