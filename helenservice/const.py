HTTP_READ_TIMEOUT = 30

# Resolution constants for API requests
RESOLUTION_HOUR = "hour"
RESOLUTION_QUARTER = "quarter"

# Ubisecure OAuth 2.0 authorization endpoint and fixed parameters
HELEN_LOGIN_API_VERSION = "v21"
HELEN_CLIENT_ID = "239967c8-c1b3-4786-9cc9-035b181bfa75"
HELEN_AUTH_ENDPOINT = "https://login.helen.fi/uas/oauth2/authorization"
HELEN_SESSION_RENEWAL_URL = "https://api.oma.helen.fi/v21/login?redirect=https://web.oma.helen.fi/personal&lang=fi"
HELEN_AUTH_PARAMS = {
    "response_type": "code",
    "scope": "openid offline_access",
    "template": "integrated",
    "client_id": HELEN_CLIENT_ID,
    "redirect_uri": "https://www.helen.fi/authResponse",
    "state": "s:a|l:fi",
    "locale": "fi",
}
