"""Offline terminal guard; pending fills require an explicit app recovery action."""
from quant_research.serde import InputError
from .service import Service


def check_accounting(root):
    intents=Service(root)._read_intents()
    if any(row['status']=='pending' for row in intents):
        raise InputError('Pending simulated fill. Open Portfolio and use Recover pending accounting before restarting the runner.')
