HTTP_READ_TIMEOUT = 30

# Resolution constants for API requests
RESOLUTION_HOUR = "hour"
RESOLUTION_QUARTER = "quarter"

# Ubisecure OAuth 2.0 authorization endpoint and fixed parameters
HELEN_LOGIN_API_VERSION = "v21"
HELEN_AUTH_ENDPOINT = "https://login.helen.fi/uas/oauth2/authorization"
HELEN_AUTH_PARAMS = {
    "response_type": "code",
    "scope": "openid", # 'openid offline_access' for refresh-token
    "template": "integrated",
    "client_id": "239967c8-c1b3-4786-9cc9-035b181bfa75",
    "redirect_uri": "https://www.helen.fi/authResponse",
    "state": "s:a|l:fi",
    "locale": "fi",
}
