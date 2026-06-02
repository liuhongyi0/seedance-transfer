"""
Creem Content Moderation API — required for all AI generation endpoints.
Screens user prompts before forwarding to AI models.

Docs: https://docs.creem.io/features/moderation
"""
import os
import httpx
from fastapi import HTTPException
from log_config import get_logger

logger = get_logger(__name__)

CREEM_API_KEY = os.getenv("CREEM_API_KEY", "")
CREEM_MODERATION_URL = "https://api.creem.io/v1/moderation/prompt"
CREEM_MODERATION_TIMEOUT = 5.0  # seconds


async def screen_prompt(prompt: str, external_id: str = "") -> bool:
    """
    Screen a user prompt via Creem Moderation API before generation.
    Returns True if the prompt is allowed, raises HTTPException if denied.

    Rules:
    - "allow" → forward to generation
    - "flag"  → treat as deny (block)
    - "deny"  → block with error
    - API failure → fail closed (block, do not generate)
    """
    if not CREEM_API_KEY or not CREEM_API_KEY.startswith("creem_"):
        # No Creem key configured — skip moderation (dev/self-hosted)
        logger.warning("No Creem API key; skipping content moderation")
        return True

    if not prompt or not prompt.strip():
        return True  # empty prompt is validated elsewhere

    try:
        async with httpx.AsyncClient(timeout=CREEM_MODERATION_TIMEOUT) as http:
            resp = await http.post(
                CREEM_MODERATION_URL,
                headers={
                    "x-api-key": CREEM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": prompt.strip()[:3000],  # truncate to reasonable length
                    "external_id": external_id[:200] if external_id else "",
                },
            )

            if resp.status_code != 200:
                logger.error(f"Moderation API returned {resp.status_code}: {resp.text[:200]}")
                # Fail closed — block generation
                raise HTTPException(
                    status_code=503,
                    detail="Content moderation is temporarily unavailable. Please try again later."
                )

            data = resp.json()
            decision = data.get("decision", "deny")

            if decision == "allow":
                logger.debug(f"Moderation: ✅ ALLOWED — {external_id}")
                return True

            # flag or deny → block
            logger.warning(f"Moderation: 🚫 {decision.upper()} — {external_id} — prompt: {prompt[:100]}")
            raise HTTPException(
                status_code=400,
                detail="Your prompt contains prohibited content and was blocked by our content safety system. Please revise your prompt and try again."
            )

    except HTTPException:
        raise  # re-raise our own HTTPException
    except httpx.TimeoutException:
        logger.error("Moderation API timed out")
        raise HTTPException(
            status_code=503,
            detail="Content moderation service timed out. Please try again later."
        )
    except Exception as e:
        logger.error(f"Moderation API error: {e}")
        # Fail closed — block generation
        raise HTTPException(
            status_code=503,
            detail="Content moderation check failed. Please try again later."
        )
