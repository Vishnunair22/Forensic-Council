import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Test keys
TEST_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCmZRw6lXkEaM73
5+f7xJL/0Vaij+pED9KTnEoZ3fsYXYETMuP13j5D+bbIFE2CKOTfjZRuYzrhsVGM
3DyJkI+WM4xWHcWC42/QCDR/sGexVG7qISFaHWyG98tU579iWGKA8g5RE+vP9YHg
cYy+0l4HTHiqHfE9rGyREenSurCv6M93eNarRb5mLYjHEZszHJqJWiu/a6uPkrvG
ElLNNVO1/M9nXBQvSWB7Qc1AXaizDfr1QFmKb3WOZLnCa3b0puzb3HDIE4CJgqmg
CEJUDw3z4Zq4b8MI2T30tHaa1kBuOSRuPvO0vsTNKRKQqJlj/Lt60OUYndbSgNel
SszY8ZeZAgMBAAECggEABFQeSEBd7/FNjAmsgWJPXCgNF8jEZH2gYd5nl5VsnClH
i7Ev2LQtvL005e7QRt3rOU0Qss/yRs+C8nYCvaXk9Fh2MsHOwu1JefkSq40yX1y1
z3Gp8VMRYQ/2akimlAd+VYImgPGymVv2w1jU21xz3X795xgFD/CJuPrlMSoR4VuT
c3whvv9TgNHl9oQMnmIC7PY9wiz7ZPMvSfsDuIdWwAapjS3R2m8Ef3X2PBT9Z3mA
Td0UNQISFBv9vt4LoYspZs9S5lo7WDrocWnB0Lpq3hr35nxb06cDFt5v/8yAv1f+
vr99fMRCiUMnLPdd0MFMqg6HfomAGKTPu5Z5OIUmUQKBgQDasmX9Yo3m1kaVAuyC
svS1iomDZdty0rxJs7ztnIGn7XVJX+bShwC/anvAE5HJuryDD9hEieYxVkAgERPq
uAJWHLdJ1L7geUQMYZt5Q95trUsIRj1aErS6JaWZQocB0CC22dJWI2v0czpTN2V/
/JuIUw+mCekurS3Y4J4nf/INqQKBgQDCxuaOHFq+hSlyxmBs4XA+MWlyjLGG/675
fS50l/uJMTifcsilOunLzrEJnvUg/QZdzsmxUmfOTL3bpuZd4ZDewGM6yEpnWN06
0tgwWuorQxC5dNeS8pnAbx9AadvhCTvogOy9XM5nibXsDxjAARYYd7QZkHrwT/ua
a/mvzacQcQKBgBHu2woiELzDCVqiuL4m6oYQbCJIMeyCd0ob4Pwi/0bD5AA2Svks
dNU9aBRiBmxiUZ71p6hHHochKXT3sYhnullRVX5KYbSKfRf+0P7qn8yijyqIh/Ng
4Uz6VU/x8pwlculLh0Hk+a8726aDPmF2V1KgbQISgfp/3OiR0qYuiayxAoGAPxiL
q1GIG9urN6EHr33ADIWZMSBeierd1bg1ilOJikHFo/FdChlxjzIfq4wwwET3AQBx
2d1l/zBg+Hyyd4sQkPglrO8hGyVwVRPkMJXi8azCCDHPe6zXHb1hlE42ikmhfIn3
JsifnG7B3fxt+hTgAYEVeIqTKLHgQX/k3Ix0KCECgYBI57jRsJ3stSqXXx7qxIWe
9Rs5ryszLZRTlA48LVdNQbzC46iSA9Qh6koVOGznWczNq1OBDfRQTXLiN/FbkjhT
eHa5JF5eRcHGuobEcv5fxMVeuGV6XhPPuMPryrIiCUpWqv76hvIzlYuT/cHQMkZ0
TcUNfi1iaVltq4y/ghJiEw==
-----END PRIVATE KEY-----"""

TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApmUcOpV5BGjO9+fn+8SS
/9FWoo/qRA/Sk5xKGd37GF2BEzLj9d4+Q/m2yBRNgijk342UbmM64bFRjNw8iZCP
ljOMVh3FguNv0Ag0f7BnsVRu6iEhWh1shvfLVOe/YlhigPIOURPrz/WB4HGMvtJe
B0x4qh3xPaxskRHp0rqwr+jPd3jWq0W+Zi2IxxGbMxyaiVorv2urj5K7xhJSzTVT
tfzPZ1wUL0lge0HNQF2osw369UBZim91jmS5wmt29Kbs29xwyBOAiYKpoAhCVA8N
8+GauG/DCNk99LR2mtZAbjkkbj7ztL7EzSkSkKiZY/y7etDlGJ3W0oDXpUrM2PGX
mQIDAQAB
-----END PUBLIC KEY-----"""

os.environ["APP_ENV"] = "testing"
os.environ["JWT_ALGORITHM"] = "RS256"
os.environ["JWT_PRIVATE_KEY"] = TEST_PRIVATE_KEY
os.environ["JWT_PUBLIC_KEY"] = TEST_PUBLIC_KEY

import jwt
from fastapi import HTTPException

from core.auth import (
    UserRole,
    create_access_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from core.config import get_settings

get_settings.cache_clear()  # Force reload with environment variables


class TestRS256Auth:
    @pytest.mark.asyncio
    async def test_create_and_decode_rs256(self):
        """Test token creation and decoding with RS256 algorithm."""
        with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
            token = create_access_token("user_rs256", UserRole.INVESTIGATOR, username="tester")
            token_data = await decode_token(token)

            assert token_data.user_id == "user_rs256"
            assert token_data.username == "tester"
            assert token_data.role == UserRole.INVESTIGATOR

    @pytest.mark.asyncio
    async def test_decode_token_audience_mismatch(self):
        """Test that tokens with incorrect audience are rejected."""
        with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
            # Create token manually with wrong aud
            payload = {
                "sub": "user_123",
                "role": UserRole.INVESTIGATOR,
                "username": "tester",
                "aud": "wrong-audience",
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            }
            token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

            with pytest.raises(HTTPException) as exc:
                await decode_token(token)
            assert exc.value.status_code == 401
            assert "Invalid or expired token" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_decode_token_algorithm_downgrade(self):
        """Test protection against algorithm downgrade attacks."""
        with patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=False)):
            # Try to sign with HS256 using a dummy secret
            # The server will reject it because it's not RS256
            payload = {
                "sub": "user_123",
                "role": UserRole.INVESTIGATOR,
                "aud": "forensic-council-api",
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            }
            token = jwt.encode(payload, "dummy-secret", algorithm="HS256")

            with pytest.raises(HTTPException) as exc:
                await decode_token(token)
            assert exc.value.status_code == 401

    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = "strong-password-123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong-password", hashed)

    def test_password_truncation(self):
        """Test that passwords longer than 72 bytes are rejected."""
        long_password = "a" * 100
        with pytest.raises(ValueError, match="exceeds the 72-byte"):
            get_password_hash(long_password)

    @pytest.mark.asyncio
    @patch("core.auth.is_token_blacklisted", new=AsyncMock(return_value=True))
    async def test_decode_token_revoked(self):
        """Test that blacklisted tokens are rejected."""
        token = create_access_token("revoked", UserRole.INVESTIGATOR)
        with pytest.raises(HTTPException) as exc:
            await decode_token(token)
        assert exc.value.status_code == 401
        assert "revoked" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_require_role_dependency(self):
        """Test role-based access control dependency."""
        from core.auth import require_role

        user = MagicMock(role=UserRole.INVESTIGATOR)
        checker = require_role(UserRole.INVESTIGATOR)
        # Should pass
        result = await checker(current_user=user)
        assert result == user

        # Should fail for different role
        checker_admin = require_role(UserRole.ADMIN)
        with pytest.raises(HTTPException) as exc:
            await checker_admin(current_user=user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch("core.auth.decode_token")
    @patch("core.persistence.postgres_client.get_postgres_client")
    async def test_get_current_user_success(self, mock_pg, mock_decode):
        from core.auth import TokenData, get_current_user

        mock_decode.return_value = TokenData(
            user_id="u1", username="test", role=UserRole.INVESTIGATOR
        )

        # Mock postgres return (is_disabled = False)
        mock_conn = AsyncMock()
        mock_conn.fetch_one.return_value = {"is_disabled": False}
        mock_pg.return_value = mock_conn

        mock_request = MagicMock()
        mock_creds = MagicMock(credentials="valid-token")

        user = await get_current_user(mock_request, credentials=mock_creds)
        assert user.user_id == "u1"
        assert user.role == UserRole.INVESTIGATOR

    @pytest.mark.asyncio
    @patch("core.auth.decode_token")
    @patch("core.persistence.postgres_client.get_postgres_client")
    async def test_get_current_user_disabled(self, mock_pg, mock_decode):
        from core.auth import TokenData, get_current_user

        mock_decode.return_value = TokenData(
            user_id="u1", username="test", role=UserRole.INVESTIGATOR
        )

        # Mock postgres return (is_disabled = True)
        mock_conn = AsyncMock()
        mock_conn.fetch_one.return_value = {"is_disabled": True}
        mock_pg.return_value = mock_conn

        mock_request = MagicMock()
        mock_creds = MagicMock(credentials="valid-token")

        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, credentials=mock_creds)
        assert exc.value.status_code == 403

    def test_cleanup_expired_local_blacklist(self):
        """Test that expired local blacklist entries are removed."""
        import time

        from core.auth import _cleanup_local_blacklist, _recently_blacklisted

        _recently_blacklisted["expired"] = time.time() - 10
        _recently_blacklisted["valid"] = time.time() + 10

        _cleanup_local_blacklist()

        assert "expired" not in _recently_blacklisted
        assert "valid" in _recently_blacklisted
        _recently_blacklisted.clear()

    def test_create_token_with_delta(self):
        """Test token creation with custom expiration delta."""
        delta = timedelta(hours=2)
        token = create_access_token("u1", UserRole.INVESTIGATOR, expires_delta=delta)
        # We can't easily check 'exp' without decoding, but decode_token will check it
        assert token is not None

    @pytest.mark.asyncio
    async def test_decode_token_missing_sub(self):
        """Test that tokens missing mandatory claims are rejected."""
        payload = {"role": UserRole.INVESTIGATOR.value, "aud": "forensic-council-api"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")
        with pytest.raises(HTTPException) as exc:
            await decode_token(token)
        # It might be 401 from JWTError or our explicit check
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch("core.persistence.postgres_client.get_postgres_client")
    async def test_get_current_user_cookie_fallback(self, mock_pg):
        from core.auth import TokenData, get_current_user

        mock_request = MagicMock()
        mock_request.cookies = {"access_token": "cookie-token"}

        with patch("core.auth.decode_token") as mock_decode:
            mock_decode.return_value = TokenData(
                user_id="u1", username="test", role=UserRole.INVESTIGATOR
            )
            mock_conn = AsyncMock()
            mock_conn.fetch_one.return_value = {"is_disabled": False}
            mock_pg.return_value = mock_conn

            user = await get_current_user(mock_request, credentials=None)
            assert user.user_id == "u1"

    @pytest.mark.asyncio
    @patch("core.persistence.postgres_client.get_postgres_client")
    async def test_get_current_user_optional(self, mock_pg):
        from core.auth import TokenData, get_current_user_optional

        # Unauthenticated
        mock_request = MagicMock()
        mock_request.cookies = {}
        assert await get_current_user_optional(request=mock_request, credentials=None) is None

        # Authenticated
        mock_creds = MagicMock(credentials="token")
        with patch("core.auth.decode_token") as mock_decode:
            mock_decode.return_value = TokenData(
                user_id="u1", username="test", role=UserRole.INVESTIGATOR
            )
            user = await get_current_user_optional(request=mock_request, credentials=mock_creds)
            assert user.user_id == "u1"
