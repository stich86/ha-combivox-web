"""Authentication module for Combivox Amica Web."""

import base64
import logging
import random
import asyncio
from typing import Optional, Tuple

import aiohttp

from .const import PERMMANUAL, LOGIN_URL, LOGIN2_URL

_LOGGER = logging.getLogger(__name__)


class CombivoxAuth:
    """Manage authentication with Combivox Amica."""

    def __init__(self, ip_address: str, code: str, port: int = 80, timeout: int = 10):
        """
        Initialize the authentication handler.

        Args:
            ip_address: Panel IP address
            code: User code for authentication
            port: Panel HTTP port
            timeout: Timeout for HTTP requests
        """
        self.ip_address = ip_address
        self.code = code
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{ip_address}:{port}"
        self._cookie: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    def _generate_password(self, username: str = "admin") -> Tuple[str, str]:
        """
        Generate dynamic password as per bash script esempio_insert.sh

        Args:
            username: Username for authentication (default: "admin")

        Returns:
            Tuple (password, base64_auth)
        """
        # Generate random PERMGEN (Python standard library only)
        PERMGEN = random.sample(range(1, 9), 8)

        # Generate random numbers
        RAND_LAST = random.randint(0, 99)
        RAND_LAST = f"{RAND_LAST:02d}"

        RAND_BEGIN = random.randint(0, 99)
        RAND_BEGIN = f"{RAND_BEGIN:02d}"

        _LOGGER.debug("Username: %s", username)

        # TVALUE1 = CODE + RAND_LAST
        # Note: For technical codes (8 digits), this follows the same logic as user codes
        # The JavaScript adds 2 random digits regardless of code length (if >= 6)
        TVALUE1 = self.code + RAND_LAST

        # TVALUE2 = apply PERMMANUAL
        TVALUE2 = ""
        for t in PERMMANUAL:
            NEWNUMBER = TVALUE1[t - 1]
            TVALUE2 += NEWNUMBER

        # TVALUE3 = apply PERMGEN
        TVALUE3 = ""
        for t in PERMGEN:
            NEWNUMBER = TVALUE2[t - 1]
            TVALUE3 += NEWNUMBER

        # TVALUE4PERMGEN = PERMGEN - 1 for each element
        TVALUE4PERMGEN = ""
        for t in PERMGEN:
            NEWNUMBER = str(t - 1)
            TVALUE4PERMGEN += NEWNUMBER

        # TVALUE4 = RAND_BEGIN + TVALUE3 + TVALUE4PERMGEN
        password = RAND_BEGIN + TVALUE3 + TVALUE4PERMGEN

        _LOGGER.debug("Generated password: %s", password)

        # Base64 encoding with username
        credentials = f"{username}:{password}"
        b64_auth = base64.b64encode(credentials.encode()).decode()

        _LOGGER.debug("Base64 string: %s", b64_auth)

        return password, b64_auth

    async def authenticate(self, username: str = "admin") -> bool:
        """
        Execute authentication and save the cookie.

        Args:
            username: Username for authentication (default: "admin")

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Generate password and base64 auth
            _, b64_auth = self._generate_password(username)

            # Create aiohttp session with cookie jar
            cookie_jar = aiohttp.CookieJar(quote_cookie=False)
            connector = aiohttp.TCPConnector(force_close=False)
            self._session = aiohttp.ClientSession(cookie_jar=cookie_jar, connector=connector)

            # Build URL with Basic auth as query parameter (as in bash script)
            # NOTE: "http://IP/login.cgi?Basic%20${B64}"
            login_url = f"{self.base_url}{LOGIN_URL}?Basic%20{b64_auth}"
            login2_url = f"{self.base_url}{LOGIN2_URL}?Basic%20{b64_auth}"

            # Data payload
            data = {"Basic": b64_auth}

            # First call to login.cgi
            _LOGGER.debug("Calling %s", login_url)

            async with self._session.post(
                login_url,
                data=data,
                timeout=self.timeout
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Error login.cgi: HTTP status %d, payload=%s", response.status, data)
                    await self.close()
                    return False

                _LOGGER.debug("Response login.cgi: HTTP status:%d, payload=%s", response.status, data)

            # Delay 1 second
            await asyncio.sleep(1)

            # Second call to login2.cgi with timing
            _LOGGER.debug("Calling %s with timing", login2_url)

            for delay in [2, 3, 4, 5, 6, 7]:
                await asyncio.sleep(1)

                async with self._session.post(
                    login2_url,
                    data=data,
                    timeout=self.timeout
                ) as response:
                    # Check for cookie in response
                    if response.cookies:
                        # Take the first cookie
                        for cookie_name, cookie_value in response.cookies.items():
                            self._cookie = f"{cookie_name}={cookie_value.value}"
                            _LOGGER.info("Authentication successful to Combivox panel at %s:%s", self.ip_address, self.port)
                            _LOGGER.debug("All response cookies: %s", dict(response.cookies))
                            return True

                    # Also check in session cookie_jar
                    if self._session.cookie_jar:
                        for cookie in self._session.cookie_jar:
                            self._cookie = f"{cookie}={self._session.cookie_jar[cookie]}"
                            _LOGGER.info("Authentication successful to Combivox panel at %s:%s", self.ip_address, self.port)
                            _LOGGER.debug("All session cookies: %s", dict(self._session.cookie_jar))
                            return True

            _LOGGER.error("No cookie found after authentication")
            await self.close()
            return False

        except Exception as e:
            _LOGGER.error("Error during authentication: %s", e)
            await self.close()
            return False

    def get_cookie(self) -> Optional[str]:
        """Return the session cookie."""
        return self._cookie

    def get_session(self) -> Optional[aiohttp.ClientSession]:
        """Return the authenticated HTTP session."""
        return self._session

    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        return self._cookie is not None and self._session is not None

    def generate_auth_for_command(self, username: str = "admin") -> str:
        """
        Generate Base64 authentication for command execution.

        This method generates a fresh password and returns Base64 auth
        that can be used for commands like execChangeImp.xml.

        Args:
            username: Username for authentication (default: "admin")

        Returns:
            Base64 encoded authentication string
        """
        _, b64_auth = self._generate_password(username)
        return b64_auth

    async def close(self):
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
            self._cookie = None
