"""Template-based SYNTHETIC dispute/ticket text with noise. Labels are the generating category
(with ~4% deliberate label noise), so classifier accuracy on this data is optimistic."""
from __future__ import annotations

import numpy as np
import pandas as pd

CATEGORIES = ["pricing_error", "short_shipment", "damaged_goods", "late_delivery",
              "duplicate_invoice", "payment_not_applied", "tax_vat_query"]

_T = {
    "pricing_error": [
        "unit price on invoice {inv} does not match the agreed contract price",
        "we were charged {pct} percent more than quoted for item {item}",
        "wrong price billed, our price list says a lower rate for {item}",
        "discount missing on invoice {inv}, please reissue with correct pricing",
    ],
    "short_shipment": [
        "only part of the order arrived, {n} units missing from delivery",
        "quantity received is less than invoiced for {item}, shortage of {n} pieces",
        "short shipment: invoice {inv} bills full quantity but we got fewer boxes",
        "delivery incomplete, {n} cartons not received",
    ],
    "damaged_goods": [
        "goods arrived damaged, {n} items broken in transit",
        "packaging was crushed and product {item} is defective on arrival",
        "damaged pallet received, requesting credit note for faulty units",
        "items cracked on delivery, photos attached, invoice {inv} disputed",
    ],
    "late_delivery": [
        "shipment arrived {n} days late, we request a penalty deduction",
        "delivery was delayed beyond the agreed date so we are withholding payment",
        "late arrival of goods caused a production stop, invoice {inv} disputed",
        "order delivered well after the promised delivery date",
    ],
    "duplicate_invoice": [
        "invoice {inv} appears twice in our system, please cancel the duplicate",
        "we received the same invoice two times for one delivery",
        "duplicate billing detected for order, amount charged double",
        "this invoice is a repeat of an earlier one already paid",
    ],
    "payment_not_applied": [
        "we paid invoice {inv} last month but it still shows as open on the statement",
        "remittance sent by bank transfer, payment not allocated to our account",
        "payment made on time yet reminder received, please apply the cash",
        "bank transfer reference {ref} has not been matched to the invoice",
    ],
    "tax_vat_query": [
        "vat rate on invoice {inv} looks wrong, please confirm the tax code",
        "tax amount incorrect, we are exempt and should not be charged vat",
        "missing vat registration number on the invoice, cannot reclaim tax",
        "sales tax charged on a zero rated item {item}",
    ],
}
# shared distractor phrases appear in every class, so the label is not trivially separable
_FILLER = ["please advise", "urgent", "kindly respond", "as discussed on the phone", "thank you", "see attached",
           "second reminder", "regards from accounts payable", "order ref {ref}", "contact our buyer"]
_ABBR = {"invoice": "inv", "quantity": "qty", "delivery": "dlvry", "payment": "pmt", "received": "rcvd"}


def _noise(rng, text: str) -> str:
    words = text.split()
    out = []
    for w in words:
        r = rng.random()
        if r < 0.04 and len(w) > 4:  # typo: swap two chars
            i = int(rng.integers(1, len(w) - 2))
            w = w[:i] + w[i + 1] + w[i] + w[i + 2:]
        elif r < 0.07 and w in _ABBR:
            w = _ABBR[w]
        elif r < 0.09:
            continue  # dropped word
        out.append(w)
    return " ".join(out)


def make_ticket_text(rng, cat: str) -> str:
    base = _T[cat][int(rng.integers(len(_T[cat])))]
    fill = lambda s: s.format(inv=f"{int(rng.integers(9000000, 9099999)):010d}", pct=int(rng.integers(3, 25)),
                              item=f"B{int(rng.integers(1, 40)):04d}", n=int(rng.integers(2, 60)),
                              ref=f"R{int(rng.integers(10000, 99999))}")
    parts = [fill(base)]
    for _ in range(int(rng.integers(0, 3))):
        parts.insert(int(rng.integers(0, 2)) * len(parts), fill(_FILLER[int(rng.integers(len(_FILLER)))]))
    if rng.random() < 0.15:  # mixed-signal ticket: a sentence from another class
        other = [c for c in CATEGORIES if c != cat][int(rng.integers(len(CATEGORIES) - 1))]
        parts.append(fill(_T[other][int(rng.integers(len(_T[other])))]))
    return _noise(rng, ", ".join(parts))


def make_tickets(rng, inv: pd.DataFrame, seed: int) -> pd.DataFrame:
    n = len(inv)
    probs = np.array([0.2, 0.17, 0.12, 0.15, 0.1, 0.14, 0.12])
    cats = rng.choice(CATEGORIES, size=n, p=probs)
    texts = [make_ticket_text(rng, c) for c in cats]
    flip = rng.random(n) < 0.04
    labels = np.where(flip, rng.choice(CATEGORIES, size=n), cats)
    return pd.DataFrame({"TICKET_ID": [f"T{i + 1:06d}" for i in range(n)], "VBELN_VF": inv["VBELN_VF"].to_numpy(),
                         "CREATED": inv["FKDAT"].to_numpy() + pd.Timedelta(days=7), "DESCRIPTION": texts, "CATEGORY": labels})
