from collections import Counter
import re
from typing import Dict


def analyze_log_errors(log_text: str) -> Dict[str, int]:
    if not log_text:
        return {}

    errors = re.findall(r"(ERROR|Exception|Traceback|Timeout)", log_text)
    return dict(Counter(errors))
