"""Tools the Larkspur agents can call.

The default toolset is deliberately vulnerable. With fixed=True the same tools
enforce their rules in code instead of trusting the model.
"""

import json

STAFF = "staff:triage"
TRIAGE_REFUND_LIMIT_CENTS = 5000


class ToolError(Exception):
    pass


def _schema(name, description, properties=None, required=()):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {},
            "required": list(required),
        },
    }


ORDER_ID = {"type": "string", "description": "Order ID, for example A-1001"}
TICKET_ID = {"type": "integer", "description": "Ticket number"}
REFUND_PROPS = {
    "order_id": ORDER_ID,
    "amount_cents": {"type": "integer", "description": "Refund amount in cents"},
    "reason": {"type": "string", "description": "Short reason for the refund"},
}


class Toolset:
    def __init__(self, conn, actor, fixed=False):
        self.conn = conn
        self.actor = actor
        self.fixed = fixed
        self.is_staff = actor == STAFF
        self.tools = self._build()

    def _build(self):
        tools = {
            "get_order": (self.get_order, _schema(
                "get_order", "Look up an order by its ID.", {"order_id": ORDER_ID}, ["order_id"])),
        }
        if self.is_staff:
            tools["list_open_tickets"] = (self.list_open_tickets, _schema(
                "list_open_tickets", "List open support tickets."))
            tools["read_ticket"] = (self.read_ticket, _schema(
                "read_ticket", "Read the full text of a support ticket.",
                {"ticket_id": TICKET_ID}, ["ticket_id"]))
            tools["close_ticket"] = (self.close_ticket, _schema(
                "close_ticket", "Close a ticket with a short resolution note.",
                {"ticket_id": TICKET_ID, "resolution": {"type": "string"}},
                ["ticket_id", "resolution"]))
            if self.fixed:
                # Fix for FL-01/FL-04: the agent that reads untrusted tickets cannot move money.
                tools["propose_refund"] = (self.propose_refund, _schema(
                    "propose_refund", "Propose a refund for a human to approve.",
                    REFUND_PROPS, ["order_id", "amount_cents", "reason"]))
            else:
                tools["issue_refund"] = (self.issue_refund, _schema(
                    "issue_refund", "Refund money for an order immediately.",
                    REFUND_PROPS, ["order_id", "amount_cents", "reason"]))
        else:
            tools["list_my_orders"] = (self.list_my_orders, _schema(
                "list_my_orders", "List the current customer's orders."))
            tools["issue_refund"] = (self.issue_refund, _schema(
                "issue_refund", "Refund money for one of the customer's orders.",
                REFUND_PROPS, ["order_id", "amount_cents", "reason"]))
        return tools

    def schemas(self):
        return [schema for _, schema in self.tools.values()]

    def call(self, name, args):
        entry = self.tools.get(name)
        if entry is None:
            ok, result = False, {"error": f"unknown tool: {name}"}
        else:
            try:
                ok, result = True, entry[0](**args)
            except (ToolError, TypeError, ValueError) as exc:
                ok, result = False, {"error": str(exc)}
        self.conn.execute(
            "INSERT INTO audit (actor, tool, args, ok, result) VALUES (?, ?, ?, ?, ?)",
            (self.actor, name, json.dumps(args), int(ok), json.dumps(result)),
        )
        self.conn.commit()
        return json.dumps(result)

    def _order(self, order_id):
        row = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ToolError("no such order")
        # Fix for FL-02: customers can only reach their own orders, whatever the model asks for.
        if self.fixed and not self.is_staff and row["customer_id"] != self.actor:
            raise ToolError("no such order")
        return row

    def _refunded_cents(self, order_id):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM refunds WHERE order_id = ?", (order_id,)
        ).fetchone()
        return row[0]

    def _record_refund(self, order_id, amount_cents, reason, approved):
        self.conn.execute(
            "INSERT INTO refunds (order_id, amount_cents, reason, requested_by, approved)"
            " VALUES (?, ?, ?, ?, ?)",
            (order_id, amount_cents, reason, self.actor, int(approved)),
        )
        self.conn.commit()

    def get_order(self, order_id):
        return dict(self._order(order_id))

    def list_my_orders(self):
        rows = self.conn.execute(
            "SELECT id, item, total_cents, status FROM orders WHERE customer_id = ?", (self.actor,)
        ).fetchall()
        return [dict(row) for row in rows]

    def issue_refund(self, order_id, amount_cents, reason):
        order = self._order(order_id)
        amount_cents = int(amount_cents)
        if self.fixed:
            # Fix for FL-04: amount checked in code, and a human approves every refund.
            if amount_cents <= 0 or self._refunded_cents(order_id) + amount_cents > order["total_cents"]:
                raise ToolError("amount exceeds the refundable balance")
            self._record_refund(order_id, amount_cents, reason, approved=False)
            return {"status": "pending_review", "message": "A team member will review this refund."}
        self._record_refund(order_id, amount_cents, reason, approved=True)
        return {"status": "refunded", "order_id": order_id, "amount_cents": amount_cents}

    def propose_refund(self, order_id, amount_cents, reason):
        order = self._order(order_id)
        amount_cents = int(amount_cents)
        if amount_cents <= 0 or self._refunded_cents(order_id) + amount_cents > order["total_cents"]:
            raise ToolError("amount exceeds the refundable balance")
        self._record_refund(order_id, amount_cents, reason, approved=False)
        return {"status": "pending_review"}

    def list_open_tickets(self):
        rows = self.conn.execute(
            "SELECT id, customer_id, subject FROM tickets WHERE status = 'open'"
        ).fetchall()
        return [dict(row) for row in rows]

    def read_ticket(self, ticket_id):
        row = self.conn.execute("SELECT * FROM tickets WHERE id = ?", (int(ticket_id),)).fetchone()
        if row is None:
            raise ToolError("no such ticket")
        return dict(row)

    def close_ticket(self, ticket_id, resolution):
        cur = self.conn.execute(
            "UPDATE tickets SET status = 'closed', resolution = ? WHERE id = ?",
            (resolution, int(ticket_id)),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            raise ToolError("no such ticket")
        return {"status": "closed"}
