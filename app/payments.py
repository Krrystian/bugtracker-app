"""Payment provider client configuration.

INTENTIONALLY VULNERABLE (branch vuln/secret-leak only).
"""

# VULN-01: hard-coded API key committed to the repository. The value is a
# random, fake key that does not work anywhere (demonstration only).
PAYMENT_API_KEY = "d02462e96642180c17fc19acd4dcbeec12e90bdbbacb774d"
PAYMENT_API_URL = "https://payments.invalid/v1"
