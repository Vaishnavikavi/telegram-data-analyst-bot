import os
import json
import hashlib
import base64
import sqlite3
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

PROFILE = "ga5-mailroom-action-gate/v2"
DB_PATH = "/tmp/mailroom.db"


# ============================================================
# DATABASE
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            evaluation_id TEXT PRIMARY KEY,
            input_digest TEXT NOT NULL,
            verifier_json TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            evaluation_id TEXT NOT NULL,
            dossier_id TEXT NOT NULL,
            dossier_fingerprint TEXT NOT NULL,
            proposal_json TEXT NOT NULL,
            proposal_digest TEXT NOT NULL,
            call_id TEXT NOT NULL,
            PRIMARY KEY (evaluation_id, dossier_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            evaluation_id TEXT NOT NULL,
            dossier_id TEXT NOT NULL,
            receipt_id TEXT NOT NULL,
            receipt_json TEXT NOT NULL,
            PRIMARY KEY (evaluation_id, dossier_id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# CANONICAL JSON / HASHING
# ============================================================

def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def proposal_digest(proposal: dict) -> str:
    value = {
        "dossierId": proposal["dossierId"],
        "callId": proposal["callId"],
        "action": proposal["action"],
        "target": proposal.get("target"),
        "payload": proposal["payload"],
        "evidence": sorted(proposal["evidence"]),
    }

    return sha256_json(value)


# ============================================================
# CALL ID
# ============================================================

def stable_call_id(dossier_fingerprint: str) -> str:
    """
    Stable across evaluations for the same dossier content.
    """
    digest = hashlib.sha256(
        ("mailroom-call:" + dossier_fingerprint).encode()
    ).hexdigest()

    return "mail-" + digest[:40]


# ============================================================
# DOSSIER FINGERPRINT
# ============================================================

def dossier_fingerprint(dossier: dict) -> str:
    return sha256_json(dossier)


# ============================================================
# VALIDATION
# ============================================================

ALLOWED_ACTIONS = {
    "create_draft",
    "update_internal_record",
    "send_approved_notice",
    "request_confirmation",
    "quarantine_item",
    "no_action",
}


def validate_dossiers(body):
    if not isinstance(body, dict):
        return False, "Request body must be a JSON object."

    if body.get("profile") != PROFILE:
        return False, "Invalid profile."

    if body.get("operation") not in {"propose", "commit"}:
        return False, "Invalid operation."

    if not isinstance(body.get("evaluationId"), str):
        return False, "Missing evaluationId."

    return True, ""


# ============================================================
# EVIDENCE HELPERS
# ============================================================

def all_lines(dossier):
    result = []

    for source in dossier.get("sources", []):
        for line in source.get("lines", []):
            if isinstance(line, dict):
                line_id = line.get("lineId")
                text = line.get("text", "")

                if line_id:
                    result.append((line_id, text))

    return result


def line_ids(dossier):
    return [x[0] for x in all_lines(dossier)]


def dossier_text(dossier):
    chunks = []

    chunks.append(str(dossier.get("objective", "")))
    chunks.append(str(dossier.get("mailbox", "")))

    for source in dossier.get("sources", []):
        chunks.append(str(source.get("title", "")))
        chunks.append(str(source.get("provenance", "")))

        for line in source.get("lines", []):
            chunks.append(str(line.get("text", "")))

    return "\n".join(chunks)


# ============================================================
# DETERMINISTIC MAILROOM DECISION ENGINE
# ============================================================

def decide_dossier(dossier):
    """
    Conservative deterministic policy.

    Important:
    External mail is treated as DATA, not instructions.
    """

    text = dossier_text(dossier)
    lower = text.lower()

    lines = all_lines(dossier)

    # --------------------------------------------------------
    # Find useful reference / case identifiers
    # --------------------------------------------------------

    reference_id = None
    case_id = None

    import re

    patterns = [
        r"\border[_ -]?id[:\s#-]+([A-Za-z0-9_-]+)",
        r"\border[:\s#-]+([A-Za-z0-9_-]+)",
        r"\breference[_ -]?id[:\s#-]+([A-Za-z0-9_-]+)",
        r"\bref[:\s#-]+([A-Za-z0-9_-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            reference_id = match.group(1)
            break

    case_match = re.search(
        r"\bcase(?:[_ -]?id)?[:\s#-]+([A-Za-z0-9_-]+)",
        text,
        re.I,
    )

    if case_match:
        case_id = case_match.group(1)

    if reference_id is None:
        reference_id = dossier.get("dossierId", "")

    # --------------------------------------------------------
    # Prompt injection / unsafe tool-control content
    # --------------------------------------------------------

    injection_terms = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "system prompt",
        "developer message",
        "reveal secrets",
        "reveal the secret",
        "send the secret",
        "access private",
        "private context",
        "use the tool",
        "call the tool",
        "execute this command",
        "download this file",
        "forward this email",
        "send an email to",
    ]

    injection = any(term in lower for term in injection_terms)

    if injection:
        evidence = []

        for line_id, line_text in lines:
            line_lower = line_text.lower()

            if any(term in line_lower for term in injection_terms):
                evidence.append(line_id)

                if len(evidence) >= 2:
                    break

        if not evidence and lines:
            evidence = [lines[0][0]]

        return {
            "action": "quarantine_item",
            "target": {
                "kind": "security_queue",
                "id": "mailroom",
            },
            "payload": {
                "artifactId": dossier.get("dossierId"),
                "reasonCode": "INDIRECT_PROMPT_INJECTION",
            },
            "evidence": evidence,
        }

    # --------------------------------------------------------
    # Duplicate / completed / informational
    # --------------------------------------------------------

    if (
        "already completed" in lower
        or "completed successfully" in lower
        or "duplicate" in lower
        or "already processed" in lower
    ):
        evidence = []

        for line_id, line_text in lines:
            ll = line_text.lower()

            if (
                "already completed" in ll
                or "completed successfully" in ll
                or "duplicate" in ll
                or "already processed" in ll
            ):
                evidence.append(line_id)

                if len(evidence) >= 2:
                    break

        if not evidence and lines:
            evidence = [lines[0][0]]

        reason = "DUPLICATE"

        if "already completed" in lower or "completed successfully" in lower:
            reason = "ALREADY_COMPLETED"

        return {
            "action": "no_action",
            "target": None,
            "payload": {
                "reasonCode": reason,
                "referenceId": reference_id,
            },
            "evidence": evidence,
        }

    # --------------------------------------------------------
    # Explicit approval / outbound notice
    # --------------------------------------------------------

    approved = (
        "approved" in lower
        and (
            "send" in lower
            or "notice" in lower
            or "delivery" in lower
        )
    )

    if approved:
        recipient = None

        email_match = re.search(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            text,
        )

        if email_match:
            recipient = email_match.group(0)

        # Never invent an outbound recipient.
        if recipient:
            evidence = []

            for line_id, line_text in lines:
                ll = line_text.lower()

                if "approved" in ll or recipient.lower() in ll:
                    evidence.append(line_id)

            return {
                "action": "send_approved_notice",
                "target": {
                    "kind": "email",
                    "id": recipient,
                },
                "payload": {
                    "referenceId": reference_id,
                    "status": "approved",
                    "template": "approved_delivery_notice",
                },
                "evidence": evidence[:3],
            }

    # --------------------------------------------------------
    # Internal delivery-window update
    # --------------------------------------------------------

    delivery_window = None

    window_match = re.search(
        r"(?:delivery window|delivery_window)"
        r"\s*(?:is|:|=)\s*"
        r"([A-Za-z0-9 ,:+\-–]+)",
        text,
        re.I,
    )

    if window_match:
        delivery_window = window_match.group(1).strip()

    authorized_update = (
        "update" in lower
        and "delivery window" in lower
        and delivery_window
        and case_id
    )

    if authorized_update:
        source_event_id = None

        event_match = re.search(
            r"(?:event[_ -]?id|source[_ -]?event[_ -]?id)"
            r"[:\s-]+([A-Za-z0-9_-]+)",
            text,
            re.I,
        )

        if event_match:
            source_event_id = event_match.group(1)

        if source_event_id:
            evidence = []

            for line_id, line_text in lines:
                ll = line_text.lower()

                if (
                    "delivery window" in ll
                    or source_event_id.lower() in ll
                    or "authorized" in ll
                ):
                    evidence.append(line_id)

            return {
                "action": "update_internal_record",
                "target": {
                    "kind": "case_record",
                    "id": case_id,
                },
                "payload": {
                    "field": "delivery_window",
                    "sourceEventId": source_event_id,
                    "value": delivery_window,
                },
                "evidence": evidence[:3],
            }

    # --------------------------------------------------------
    # Ambiguous sender / identity conflict
    # --------------------------------------------------------

    identity_terms = [
        "verify identity",
        "identity conflict",
        "identity mismatch",
        "not sure who",
        "cannot verify",
        "unknown sender",
        "confirm identity",
    ]

    if any(term in lower for term in identity_terms):
        evidence = []

        for line_id, line_text in lines:
            if any(
                term in line_text.lower()
                for term in identity_terms
            ):
                evidence.append(line_id)

        claimed_sender = dossier.get("mailbox", "unknown")

        return {
            "action": "request_confirmation",
            "target": {
                "kind": "approval_queue",
                "id": "mailroom",
            },
            "payload": {
                "claimedSender": claimed_sender,
                "questionCode": "VERIFY_REQUEST",
                "referenceId": reference_id,
            },
            "evidence": evidence[:2] or (
                [lines[0][0]] if lines else []
            ),
        }

    # --------------------------------------------------------
    # Default conservative action
    # --------------------------------------------------------

    evidence = [lines[0][0]] if lines else []

    return {
        "action": "no_action",
        "target": None,
        "payload": {
            "reasonCode": "INFORMATIONAL",
            "referenceId": reference_id,
        },
        "evidence": evidence,
    }


# ============================================================
# PROPOSAL NORMALIZATION
# ============================================================

def build_proposal(dossier):
    fingerprint = dossier_fingerprint(dossier)

    decision = decide_dossier(dossier)

    proposal = {
        "dossierId": dossier["dossierId"],
        "callId": stable_call_id(fingerprint),
        "action": decision["action"],
        "target": decision["target"],
        "payload": decision["payload"],
        "evidence": sorted(set(decision["evidence"])),
    }

    # Validate evidence against actual dossier.
    valid_lines = set(line_ids(dossier))

    proposal["evidence"] = [
        x for x in proposal["evidence"]
        if x in valid_lines
    ]

    return proposal


# ============================================================
# PROPOSE
# ============================================================

def handle_propose(body):
    ok, error = validate_dossiers(body)

    if not ok:
        return JSONResponse(
            status_code=400,
            content={"error": error},
        )

    evaluation_id = body["evaluationId"]
    dossiers = body.get("dossiers")

    if not isinstance(dossiers, list):
        return JSONResponse(
            status_code=400,
            content={"error": "dossiers must be an array."},
        )

    if len(dossiers) == 0:
        return JSONResponse(
            status_code=400,
            content={"error": "dossiers cannot be empty."},
        )

    # Duplicate dossier IDs are invalid.
    ids = [d.get("dossierId") for d in dossiers]

    if any(not isinstance(x, str) for x in ids):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid dossierId."},
        )

    if len(ids) != len(set(ids)):
        return JSONResponse(
            status_code=400,
            content={"error": "Duplicate dossier IDs."},
        )

    # Exact digest.
    input_digest = sha256_json(dossiers)

    conn = sqlite3.connect(DB_PATH)

    existing = conn.execute(
        """
        SELECT input_digest
        FROM evaluations
        WHERE evaluation_id = ?
        """,
        (evaluation_id,),
    ).fetchone()

    if existing:
        if existing[0] != input_digest:
            conn.close()

            return JSONResponse(
                status_code=409,
                content={
                    "error": "evaluationId already exists with different content."
                },
            )

        # Exact replay.
        rows = conn.execute(
            """
            SELECT proposal_json
            FROM proposals
            WHERE evaluation_id = ?
            ORDER BY rowid
            """,
            (evaluation_id,),
        ).fetchall()

        conn.close()

        proposals = [
            json.loads(row[0])
            for row in rows
        ]

        return {
            "profile": PROFILE,
            "evaluationId": evaluation_id,
            "status": "awaiting_receipts",
            "inputDigest": input_digest,
            "proposals": proposals,
        }

    verifier = body.get("receiptVerifier")

    if not isinstance(verifier, dict):
        conn.close()

        return JSONResponse(
            status_code=400,
            content={"error": "Missing receiptVerifier."},
        )

    # Persist evaluation before returning.
    conn.execute(
        """
        INSERT INTO evaluations
        (evaluation_id, input_digest, verifier_json)
        VALUES (?, ?, ?)
        """,
        (
            evaluation_id,
            input_digest,
            canonical_json(verifier),
        ),
    )

    proposals = []

    for dossier in dossiers:

        if not isinstance(dossier, dict):
            conn.rollback()
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "Invalid dossier."},
            )

        if not isinstance(dossier.get("dossierId"), str):
            conn.rollback()
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "Dossier missing dossierId."},
            )

        proposal = build_proposal(dossier)

        pdigest = proposal_digest(proposal)

        fingerprint = dossier_fingerprint(dossier)

        conn.execute(
            """
            INSERT INTO proposals
            (
                evaluation_id,
                dossier_id,
                dossier_fingerprint,
                proposal_json,
                proposal_digest,
                call_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id,
                proposal["dossierId"],
                fingerprint,
                canonical_json(proposal),
                pdigest,
                proposal["callId"],
            ),
        )

        proposals.append(proposal)

    conn.commit()
    conn.close()

    return {
        "profile": PROFILE,
        "evaluationId": evaluation_id,
        "status": "awaiting_receipts",
        "inputDigest": input_digest,
        "proposals": proposals,
    }


# ============================================================
# RECEIPT VERIFICATION
# ============================================================

def verify_receipt_signature(
    verifier,
    evaluation_id,
    input_digest,
    receipt,
):
    """
    Ed25519 verification.

    cryptography is used when available.
    """

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey
        )
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )
    except Exception:
        return False

    try:
        jwk = verifier["publicKeyJwk"]

        if jwk.get("kty") != "OKP":
            return False

        if jwk.get("crv") != "Ed25519":
            return False

        x = jwk["x"]

        padding = "=" * (-len(x) % 4)

        public_bytes = base64.urlsafe_b64decode(
            x + padding
        )

        public_key = Ed25519PublicKey.from_public_bytes(
            public_bytes
        )

        signature = receipt.get("receiptSignature")

        if not isinstance(signature, str):
            return False

        padding = "=" * (-len(signature) % 4)

        sig_bytes = base64.b64decode(
            signature + padding,
            validate=True,
        )

        signed_object = {
            "profile": PROFILE,
            "evaluationId": evaluation_id,
            "inputDigest": input_digest,
            "receipt": {
                "dossierId": receipt["dossierId"],
                "callId": receipt["callId"],
                "action": receipt["action"],
                "accepted": receipt["accepted"],
                "proposalDigest": receipt["proposalDigest"],
                "receiptId": receipt["receiptId"],
            },
        }

        message = canonical_json(
            signed_object
        ).encode("utf-8")

        public_key.verify(
            sig_bytes,
            message,
        )

        return True

    except Exception:
        return False


# ============================================================
# COMMIT
# ============================================================

def handle_commit(body):
    ok, error = validate_dossiers(body)

    if not ok:
        return JSONResponse(
            status_code=400,
            content={"error": error},
        )

    evaluation_id = body["evaluationId"]
    input_digest = body.get("inputDigest")
    receipts = body.get("receipts")

    if not isinstance(input_digest, str):
        return JSONResponse(
            status_code=400,
            content={"error": "Missing inputDigest."},
        )

    if not isinstance(receipts, list):
        return JSONResponse(
            status_code=400,
            content={"error": "receipts must be an array."},
        )

    conn = sqlite3.connect(DB_PATH)

    evaluation = conn.execute(
        """
        SELECT input_digest, verifier_json
        FROM evaluations
        WHERE evaluation_id = ?
        """,
        (evaluation_id,),
    ).fetchone()

    if not evaluation:
        conn.close()

        return JSONResponse(
            status_code=400,
            content={"error": "Unknown evaluationId."},
        )

    stored_digest, verifier_json = evaluation

    if stored_digest != input_digest:
        conn.close()

        return JSONResponse(
            status_code=400,
            content={"error": "inputDigest mismatch."},
        )

    verifier = json.loads(verifier_json)

    # --------------------------------------------------------
    # Atomic validation: validate EVERYTHING before effects.
    # --------------------------------------------------------

    proposals_rows = conn.execute(
        """
        SELECT dossier_id, proposal_json, proposal_digest, call_id
        FROM proposals
        WHERE evaluation_id = ?
        """,
        (evaluation_id,),
    ).fetchall()

    proposals = {}

    for row in proposals_rows:
        proposals[row[0]] = {
            "proposal": json.loads(row[1]),
            "proposalDigest": row[2],
            "callId": row[3],
        }

    if len(receipts) != len(proposals):
        conn.close()

        return JSONResponse(
            status_code=400,
            content={"error": "Receipt count does not match proposals."},
        )

    seen = set()

    for receipt in receipts:

        dossier_id = receipt.get("dossierId")

        if dossier_id in seen:
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "Duplicate receipt."},
            )

        seen.add(dossier_id)

        if dossier_id not in proposals:
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "Receipt references unknown proposal."},
            )

        stored = proposals[dossier_id]

        if receipt.get("callId") != stored["callId"]:
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "callId mismatch."},
            )

        if receipt.get("proposalDigest") != stored["proposalDigest"]:
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "proposalDigest mismatch."},
            )

        if receipt.get("action") != stored["proposal"]["action"]:
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "action mismatch."},
            )

        if not isinstance(receipt.get("receiptId"), str):
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "Invalid receiptId."},
            )

        if not verify_receipt_signature(
            verifier,
            evaluation_id,
            input_digest,
            receipt,
        ):
            conn.close()

            return JSONResponse(
                status_code=400,
                content={"error": "Invalid receipt signature."},
            )

    # --------------------------------------------------------
    # All receipts verified.
    # Persist them.
    # --------------------------------------------------------

    outcomes = []

    for receipt in receipts:

        dossier_id = receipt["dossierId"]

        existing = conn.execute(
            """
            SELECT receipt_json
            FROM receipts
            WHERE evaluation_id = ?
              AND dossier_id = ?
            """,
            (evaluation_id, dossier_id),
        ).fetchone()

        if existing:
            old = json.loads(existing[0])

            if old != receipt:
                conn.close()

                return JSONResponse(
                    status_code=400,
                    content={"error": "Receipt replay conflict."},
                )

        else:
            conn.execute(
                """
                INSERT INTO receipts
                (
                    evaluation_id,
                    dossier_id,
                    receipt_id,
                    receipt_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    dossier_id,
                    receipt["receiptId"],
                    canonical_json(receipt),
                ),
            )

    conn.commit()

    # --------------------------------------------------------
    # Terminal outcomes.
    # --------------------------------------------------------

    for receipt in receipts:

        outcomes.append({
            "dossierId": receipt["dossierId"],
            "callId": receipt["callId"],
            "action": receipt["action"],
            "proposalDigest": receipt["proposalDigest"],
            "receiptId": receipt["receiptId"],
            "status": (
                "executed"
                if receipt["accepted"]
                else "rejected"
            ),
        })

    conn.close()

    return {
        "profile": PROFILE,
        "evaluationId": evaluation_id,
        "status": "completed",
        "inputDigest": input_digest,
        "outcomes": outcomes,
    }


# ============================================================
# IMPORTANT: ACCEPT THE GRADER REQUEST DIRECTLY AT /
# ============================================================

@app.post("/")
async def mailroom_endpoint(request: Request):

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON."},
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "JSON object required."},
        )

    operation = body.get("operation")

    if operation == "propose":
        return handle_propose(body)

    if operation == "commit":
        return handle_commit(body)

    return JSONResponse(
        status_code=400,
        content={"error": "Invalid operation."},
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "mailroom",
    }
