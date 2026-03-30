from __future__ import annotations

import unittest
from uuid import uuid4

from backend.core.exceptions import UnauthorizedAppError
from backend.core.security import create_session_token, verify_session_token


class SessionTokenTests(unittest.TestCase):
    def test_session_token_round_trip(self) -> None:
        user_id = uuid4()
        organization_id = uuid4()

        token = create_session_token(
            user_id=user_id,
            organization_id=organization_id,
            email="user@example.com",
        )
        claims = verify_session_token(token)

        self.assertEqual(claims.user_id, user_id)
        self.assertEqual(claims.organization_id, organization_id)
        self.assertEqual(claims.email, "user@example.com")

    def test_session_token_rejects_tampering(self) -> None:
        token = create_session_token(
            user_id=uuid4(),
            organization_id=uuid4(),
            email="user@example.com",
        )
        tampered = f"{token[:-1]}x"

        with self.assertRaises(UnauthorizedAppError):
            verify_session_token(tampered)


if __name__ == "__main__":
    unittest.main()
