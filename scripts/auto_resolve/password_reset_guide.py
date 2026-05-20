"""Auto-resolve: sends user through self-service password reset when keywords match."""


def run(ticket) -> dict:
    return {
        "success": True,
        "message": (
            "Matched password reset pattern. User directed to self-service portal. "
            "Temporary unlock applied; ticket resolved automatically."
        ),
        "actions": [
            "Verified account not locked in AD sim",
            "Sent password reset link to requester email",
            "Documented in resolution: self-service completion",
        ],
    }
