"""
core/legal/compliance_guard.py
Mimir RF Scanner — Transmit Hard Block

LEGAL CONTEXT
─────────────
Jurisdiction : Australia — South Australia (Adelaide)
Authority    : ACMA (Australian Communications and Media Authority)
Law          : Radiocommunications Act 1992 (Cth)
Licence held : NONE

Any transmission of RF energy without an ACMA apparatus licence
is a criminal offence under Australian law. This module exists
to make transmission structurally impossible in software.

HOW THIS WORKS
──────────────
HardwareTransmitError is raised immediately whenever any code path
attempts to call a transmit function. It is not a warning. It is
not a suggestion. The call never reaches the hardware.

Nothing in this project ever catches this exception to proceed anyway.
"""


class HardwareTransmitError(RuntimeError):
    """
    Raised when any code attempts to invoke a transmit operation.

    This exception exists because the HackRF One hardware is physically
    capable of transmitting radio signals. In Australia, transmitting
    without an ACMA apparatus licence is a criminal offence under the
    Radiocommunications Act 1992 (Cth).

    This project holds no transmitter apparatus licence. Therefore,
    no transmit path is permitted to exist in software — not even
    a path that 'just calls the function but never runs it'.

    If you see this error during development:
      - You have attempted to call a TX function somewhere in the stack.
      - Find that call and remove it entirely.
      - Do not catch this exception and proceed. Remove the TX call.
    """

    def __init__(self, attempted_function: str = "unknown"):
        self.attempted_function = attempted_function
        super().__init__(
            f"\n"
            f"╔══════════════════════════════════════════════════════════╗\n"
            f"║           TRANSMIT OPERATION BLOCKED — ILLEGAL           ║\n"
            f"╠══════════════════════════════════════════════════════════╣\n"
            f"║  Attempted TX function : {attempted_function:<33}║\n"
            f"║  Jurisdiction          : Australia (SA)                  ║\n"
            f"║  Law                   : Radiocommunications Act 1992    ║\n"
            f"║  Licence held          : NONE                            ║\n"
            f"║  Consequence           : Criminal offence                ║\n"
            f"╠══════════════════════════════════════════════════════════╣\n"
            f"║  Do NOT catch this exception and proceed.                ║\n"
            f"║  Remove the transmit call from your code entirely.       ║\n"
            f"╚══════════════════════════════════════════════════════════╝\n"
        )


def transmit_guard(function_name: str) -> None:
    """
    Call this at the top of any function that must never transmit.

    Usage:
        def some_function_that_must_not_tx(self):
            transmit_guard("some_function_that_must_not_tx")
            # ... rest of function is unreachable if guard triggers

    Args:
        function_name: The name of the blocked function, shown in the
                       error message to help locate the offending call.

    Raises:
        HardwareTransmitError: Always. This function never returns normally.
    """
    raise HardwareTransmitError(attempted_function=function_name)
